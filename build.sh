#!/usr/bin/env sh
set -eu

IMAGE_NAME="life-balance-image"
CONTAINER_NAME="life-balance-bot"

docker build --tag "$IMAGE_NAME" .

if docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    docker container rm --force "$CONTAINER_NAME"
fi

docker run \
    --detach \
    --name "$CONTAINER_NAME" \
    --restart always \
    --env BOT_DATA_DIRECTORY=/data \
    --volume life-balance-data:/data \
    "$IMAGE_NAME"
