# 開発手順

## 環境

- macOS（Apple Silicon）。会議アプリの検知が CoreAudio を、録音が PortAudio を読むため、テストも macOS で動かす
- Python と依存は [uv](https://docs.astral.sh/uv/) が管理する（`uv.lock` を追跡する）
- 周辺ツールは `nix develop`（[flake.nix](../flake.nix)）で揃う: uv、just、lefthook、gitleaks、ffmpeg、switchaudio-osx、zip。nix を使わないなら Homebrew で同じものを入れる
- BlackHole 2ch はドライバなので nix では入れない（`brew install blackhole-2ch`）

## コマンド

```sh
just setup      # uv sync + lefthook install
just lint       # ruff
just test       # pytest
just security   # Gitleaks（Git 履歴）
just verify     # lint + test + security（完了前に必ず通す）
just zip        # 共有用の zip を dist/ に作る（追跡中のファイルだけ）
```

手元で CLI を試すときは `uv run scriba ...`。実データに触れないよう、`SCRIBA_HOME` を一時フォルダに向ける。

```sh
SCRIBA_HOME="$(mktemp -d)" uv run scriba status
```

## テスト

| 種類 | 置き場 | 内容 |
|---|---|---|
| golden | `tests/test_golden.py`、`tests/golden/` | 架空のセッションに対する CLI（start → merge → stop → enrich → export の流れ、status、title、dict）とビューア（静的 HTML のデータ、HTTP の全経路と編集 API）の出力を、期待値と突き合わせる。録音プロセス・出力デバイス・通知は差し替える。入口は CLI と HTTP だけなので、内部の構成を変えても同じテストで同等性を確かめられる |
| 単体 | `tests/test_*.py` | 辞書、マージ、トラック名、カレンダーのアダプタ、分類、export、自動停止、自動録音の判定、通知 |

golden を更新するときは、差分が意図した変更だけであることを `git diff tests/golden` で確かめる。期待値のファイルがないテストは失敗する（黙って作らない）。

```sh
SCRIBA_UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py
```

テストは外部コマンド（osascript、open、SwitchAudioSource、mlx-whisper、VAD）とデバイスを呼ばない。録音、通知、会議アプリの検知、文字起こしの実行は実機で確かめる。

## コミット前の検査

`just setup` で入る lefthook が、コミットのたびに次を実行する。

- Gitleaks（ステージ済みの内容）
- ruff（ステージ済みの .py）

push の前には `just verify` が走る。

## データの場所

`{base_dir}`（既定 `~/scriba`、`SCRIBA_HOME`）の構成は [usage.md](usage.md#データの場所)。リポジトリの `z-ai/` は git 管理外の作業フォルダで、zip にも入らない。
