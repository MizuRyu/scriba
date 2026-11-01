#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Scriba Toggle
# @raycast.mode silent
# @raycast.icon 🎙️
# @raycast.packageName Scriba

# 前提: uv tool install --editable <repo> で scriba がPATHにあること
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/etc/profiles/per-user/$USER/bin:/run/current-system/sw/bin:$PATH"

if scriba status --quiet; then
  scriba stop
  echo "録音停止"
else
  scriba start
  echo "録音開始"
fi
