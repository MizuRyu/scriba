#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Scriba Auto Toggle
# @raycast.mode silent
# @raycast.icon 🎙️
# @raycast.packageName Scriba
# @raycast.description 自動録音（Teams 会議の開始・終了で録音を開始・停止）を切り替える

# 前提: uv tool install --editable <repo> で scriba がPATHにあること
# Raycast から起動するのは、録音プロセスがマイクの許可を Raycast から受け継ぐため
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/etc/profiles/per-user/$USER/bin:/run/current-system/sw/bin:$PATH"

scriba watch toggle
