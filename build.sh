#!/bin/sh

cd "$(realpath "$(dirname "$0")")"
printf "\nREMINDER: always ext/update-backends.sh after git pull\n\n" >&2
docker build -t kcri-cge-bap . | tee build.log
