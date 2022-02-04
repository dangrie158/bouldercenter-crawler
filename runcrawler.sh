#!/bin/sh

DIR=$( dirname "$0" )
cd "${DIR}"
python3.10 "${DIR}"/crawl.py
