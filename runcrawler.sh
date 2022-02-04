#!/bin/sh

DIR=$( dirname "$0" )
cd "${DIR}"
python3.7 "${DIR}"/crawl.py
