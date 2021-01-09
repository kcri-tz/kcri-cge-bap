#!/bin/sh

cd "$(realpath "$(dirname "$0")")"
docker build -t kcri-cge-bap . | tee build.log
