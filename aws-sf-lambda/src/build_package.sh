#!/bin/bash
set -ex
#script designed to work as part of Docker build process (build.sh)
rm -f /vol/*.zip
zip -r "/vol/$1.zip" main.py ./vendored
