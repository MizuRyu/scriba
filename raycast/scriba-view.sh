#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Scriba View
# @raycast.mode silent
# @raycast.icon 🎙️
# @raycast.packageName Scriba
# @raycast.description 文字起こし結果のHTMLビューアを開く

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/etc/profiles/per-user/$USER/bin:/run/current-system/sw/bin:$PATH"
scriba view
echo "ビューアを開きました"
