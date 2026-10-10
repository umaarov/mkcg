#!/usr/bin/env sh
# Removes everything CreditGateway put on the server: containers, network, volumes (case data + signing keys), images, directory.
#   deploy/teardown.sh root@host [path-to-ssh-key] [remote-dir]
set -eu
TARGET="${1:?usage: teardown.sh user@host [ssh-key] [remote-dir]}"
KEY="${2:-}"
DIR="${3:-/opt/creditgateway}"
ssh ${KEY:+-i $KEY} "$TARGET" "cd $DIR && docker compose --profile tunnel --profile https down -v --rmi all --remove-orphans; cd / && rm -rf $DIR; echo removed $DIR"
