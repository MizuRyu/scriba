# Contributing

scriba は macOS（Apple Silicon）向けの Python CLI です。変更する前に [開発手順](docs/development.md) と [仕様](docs/specs/README.md) を確認してください。

## セットアップ

```sh
nix develop      # 任意。uv / just / lefthook / gitleaks / ffmpeg / switchaudio-osx を揃える
just setup
just verify
```

`just verify` は ruff、pytest、Gitleaks、個人情報の検査をまとめて実行します。

## 守ること

- 既存の流れ（start → 録音 → 逐次文字起こし → stop → enrich → export）と、既存セッションのデータ（旧名 `teams_*` のチャンクを含む）を読めることを保ってください。CLI とビューアの出力は `tests/golden/` と突き合わせます。golden を更新するときは、差分が意図した変更だけであることを確かめてください
- 不具合は再現するテストを先に追加してください
- 実際の会議の音声・文字起こし、予定、人名、メールアドレス、社名、個人のパスを fixture・テスト・Issue に入れないでください。`acme.example` のような架空の値を使います
- 整形、構造の変更、挙動の変更を同じ変更に混ぜないでください
- 録音（マイク、BlackHole）、通知、会議アプリの検知は実機で確かめるものです。テストでは外部コマンドとデバイスを差し替えます

挙動を変えたら [docs/specs/](docs/specs/README.md) の該当箇所、利用者に見える変更なら [docs/usage.md](docs/usage.md) も更新してください。判断の理由が変わる場合は [docs/adr/](docs/adr/README.md) に追加します。

## 変更の説明に書くこと

問題、変更後の動作、実行した検査とその結果、残る制約。
