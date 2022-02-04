import configparser
from datetime import datetime
import sys
from typing import Any, Optional, TypedDict, Dict

from bs4 import BeautifulSoup
import requests
from influxdb import InfluxDBClient

InfluxConfig = TypedDict(
    "InfluxConfig",
    {"host": str, "port": int, "username": str, "password": str, "database": str},
)
SiteConfig = TypedDict("SiteConfig", {"token": str, "type": str, "area": Optional[str], "clientId": Optional[str]})
CrawlResult = TypedDict("CrawlResult", {"free": int, "active": int})

def crawl_boulderado(site_config:SiteConfig)->CrawlResult:
    url = f"https://www.boulderado.de/boulderadoweb/gym-clientcounter/index.php?mode=get&token={site_config['token']}"
    page = requests.get(url)
    soup = BeautifulSoup(page.text, "html.parser")

    data = {}
    # we can extract the number of free and active slots directly from the html
    for count_value in ("act", "free"):
        count_string = (
            soup.find("div", {"class": f"{count_value}counter-content"})
            .find("span")
            .text
        )
        count = int(count_string)
        data[count_value] = count

    return {"free": data["free"], "active": data["act"]}

def crawl_webclimber(site_config:SiteConfig)->CrawlResult:
    url = f"https://{site_config['clientid']}.webclimber.de/de/trafficlight?key={site_config['token']}"
    page = requests.get(url)
    soup = BeautifulSoup(page.text, "html.parser")

    # we get the number of free places in most cases directly from the site
    free_slots_str = soup.find("div", {"class":"status_text"}).text.strip().split()[0]
    free_slots = -1
    try:
        free_slots=int(free_slots_str)
    except ValueError:
        # free slots are not available for this location, so we just use the percentage below
        pass


    # we need to calculate the number of used slots by first calculating the number of total
    # slots. this can be derived from a percentage width of the progress bar, so we need
    # to "parse" the style attribute and extract the relative width
    style_attr_strs = soup.find("div", {"class":"bar"})["style"].split(";")
    style_attrs=dict(x.split(":") for x in style_attr_strs)
    bar_width = int(style_attrs["width"].strip()[:-1])
    # now we can calculate the number of total slots
    total_slots: int = 0
    if free_slots == -1:
        # use the percentage, so assume 100 slots
        total_slots = 100
        free_slots = 100 - bar_width
    else:
        total_slots = (free_slots // bar_width) * 100
    active_slots = total_slots - free_slots

    return {"free":free_slots, "active": active_slots}

def crawl_site(site_name:str, site_config: SiteConfig) -> CrawlResult:
    match site_config["type"]:
        case "boulderado":
            return crawl_boulderado(site_config)
        case "webclimber":
             return crawl_webclimber(site_config)
        case other:
            raise ValueError(f"unknown boulder arena type: {other} for site {site_name}.")


def create_point_message(site_name:str, site_config:SiteConfig, data: CrawlResult) -> Dict[str, Any]:
    location = site_config["location"] if "location" in site_config else site_name
    message =  {
        "measurement": "boulder_center_utilization",
        "tags": {
            "location": location
        },
        "time": datetime.utcnow().isoformat(),
        "fields": {
            "free": data["free"],
            "active": data["active"],
        },
    }
    if "area" in site_config:
        message["tags"] |= {"area": site_config["area"]}

    return message


def main():
    config = configparser.ConfigParser()
    config.read("./config.ini")
    influx_config: InfluxConfig = dict(config.items("Influx"))
    config.pop("Influx")
    influx_client = InfluxDBClient(**influx_config)

    # all remaining sections are site-definitions
    sites = config.sections()
    messages=[]
    for site_name in sites:
        site_config: SiteConfig = dict(config.items(site_name))
        try:
            site_result = crawl_site(site_name, site_config)
        except Exception as error:
            print(f"failed to crawl site: {site_name}: {error}", file=sys.stderr)
            continue
        print(f"crawled {site_name:<25}: {site_result}")
        message = create_point_message(site_name, site_config, site_result)
        messages.append(message)
    influx_client.write_points(messages)


if __name__ == "__main__":
    main()
