#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Scriba Status
# @raycast.mode compact
# @raycast.icon 🎙️
# @raycast.packageName Scriba
# @raycast.description 録音状態を表示

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/etc/profiles/per-user/$USER/bin:/run/current-system/sw/bin:$PATH"
scriba status
