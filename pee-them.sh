#!/bin/sh

[ $# -eq 1 ] || { echo "Usage: pee-them VERSION" >&2; exit 1; }
VER="$1"

docker image tag kcri-cge-bap:latest kcri-cge-bap:$VER &&
docker image tag kcri-cge-bap:latest kcri-cge-bap:prod &&
docker image save kcri-cge-bap:$VER | pee "ssh babbage docker image load" "ssh hopper docker image load" &&
ssh babbage docker image tag kcri-cge-bap:$VER kcri-cge-bap:prod &&
ssh hopper docker image tag kcri-cge-bap:$VER kcri-cge-bap:prod

