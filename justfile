[private]
default:
    @just --list

# 依存を揃え、Lefthook を現在の checkout に入れる。
setup:
    uv sync
    lefthook install

lint:
    uv run ruff check src tests .agents

# 録音・文字起こし・通知の実体は呼ばない（外部コマンドとデバイスはテスト内で差し替える）。
test:
    uv run pytest -q

# 秘密情報（Gitleaks）。
security:
    gitleaks git --no-banner --redact .

verify: lint test security

# 共有用の zip を dist/ に作る。追跡中のファイルだけを入れる（z-ai/ や .git は入らない）。
zip:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p dist
    out="dist/scriba-$(date +%Y%m%d).zip"
    rm -f "$out"
    git ls-files -z | xargs -0 zip -q --symlinks "$out"
    echo "$out"
