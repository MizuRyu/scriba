#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Scriba Listen Toggle
# @raycast.mode silent
# @raycast.icon 🎙️
# @raycast.packageName Scriba
# @raycast.description 常時録音（既定の入力を録り続け、発話だけを文字にして残す）を切り替える

# 前提: uv tool install --editable <repo> で scriba がPATHにあること
# Raycast から起動するのは、常駐プロセスがマイクの許可を Raycast から受け継ぐため
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/etc/profiles/per-user/$USER/bin:/run/current-system/sw/bin:$PATH"

scriba listen toggle
