#!/bin/bash
set -e

echo "====================BASE PACKAGES1 START===================="

apt-get update && apt-get upgrade -y

apt-get install -y --no-install-recommends \
    sudo curl wget git cron \
    xvfb x11vnc xterm net-tools

echo "====================BASE PACKAGES1 END===================="
