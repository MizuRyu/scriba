#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Scriba Toggle (Record Only)
# @raycast.mode silent
# @raycast.icon 🎙️
# @raycast.packageName Scriba
# @raycast.description 録音のみ（文字起こしはstop後にまとめて実行）

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/etc/profiles/per-user/$USER/bin:/run/current-system/sw/bin:$PATH"

if scriba status --quiet; then
  scriba stop
  echo "録音停止"
else
  scriba start --mode record-only
  echo "録音開始（record-only）"
fi
