#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Scriba Serve
# @raycast.mode silent
# @raycast.icon 🎙️
# @raycast.packageName Scriba
# @raycast.description ビューアサーバーを起動/停止（トグル）

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/etc/profiles/per-user/$USER/bin:/run/current-system/sw/bin:$PATH"

PID=$(lsof -ti :8737 2>/dev/null)
if [ -n "$PID" ]; then
  kill "$PID"
  echo "サーバー停止"
else
  nohup scriba view --serve > /dev/null 2>&1 &
  echo "サーバー起動 http://127.0.0.1:8737/"
fi
