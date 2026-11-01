# AGENTS.md

scriba — オンライン会議を macOS でローカルに録音し、逐次文字起こしする CLI（Python / uv、macOS 14.2+ / Apple Silicon）。
BlackHole 経由のシステム音声と、任意でマイクを sounddevice で 2 分チャンクに録り、Haas（speech.cpp）で文字起こしして `[相手]` / `[自分]` の時刻順テキストにまとめる。

## 仕様とガイドライン

- まず `docs/background.md` で、目的とコードに書かれていない前提（音声の経路、マイク権限の継承、1 台・1 人の前提）をつかむ
- 現行仕様は `docs/specs/` が正。索引は `docs/README.md`
- 技術判断の理由と見直し条件は `docs/adr/`。判断をやり直す前に読む
- ディレクトリ構成と「どこに何を置くか」は `docs/specs/07-project-structure.md`。新しいファイルはその表に従って置く
- 利用者向けの操作・設定・データの場所は `docs/usage.md`
- 開発コマンド、テスト（golden）、コミット前の検査は `docs/development.md`
- 案件の登録（enrich.projects の追加と検証）: `.agents/skills/add-project/SKILL.md`

## 処理の流れ

1. `scriba start`（`recording/recorder.py`）→ 出力デバイスを複数出力装置へ切り替え（`audio.py`）、録音プロセス（`capture.py`）とワーカー（`transcription/worker.py`）を別プロセスで起動し、`state.json` に記録。予定と照合（`calendar/` → `enrich.py`）して `meta.json` に書く
2. 録音プロセスは `chunks/system_NNN.wav`（と `mic_NNN.wav`）を書く。無音なら通知し、system・mic とも発話がなければ自動停止する
3. ワーカーは完成したチャンクを Haas（speech.cpp）に通し、mic は同じランタイムの Silero VAD で発話区間を求め、`transcriber.merge_session` が辞書・フィルタ・重複の畳み込みをかけて combined（`yymmdd_hhmm[_会議名].txt`）を書き直す
4. `scriba stop` → 録音を確定させて出力を戻し、残りを文字起こし。frontmatter を付け（`enrich.py`）、案件が決まっていれば転送する（`export.py`、分類は `classify.py`）
5. 自動録音（`meeting/watch.py`）は会議アプリのマイク使用（`meeting/detect.py`）を見て `scriba start` / `scriba stop` を呼ぶ
6. ビューア（`viewer/`）は `render.py` が HTML を、`server.py` が `view --serve` の HTTP と編集 API を持つ

## コマンド

```sh
nix develop      # 任意。uv, just, lefthook, gitleaks, ffmpeg, switchaudio-osx
just setup       # uv sync + lefthook install
just test        # pytest
just verify      # ruff + pytest + Gitleaks（完了前に必ず通す）
```

## 原則

- **エージェントは録音・自動録音・ビューアのサーバーを実データで起動しない。** マイク、出力デバイスの切り替え、通知は利用者の作業を妨げる。CLI を試すときは `SCRIBA_HOME` を一時フォルダに向ける。実データ（`~/scriba`）は読むだけにする
- 既存機能の挙動を変えない変更は、`tests/golden/` が変わらないことで確かめる。golden を更新するのは意図した変更のときだけで、差分を確かめてから
- 既存セッションを読めることを保つ。旧名 `teams_*` のチャンク、`meta.json` に保存されたイベント形式（ADR-004、ADR-005）
- mlx-whisper と Silero VAD を本体の依存に入れない（ADR-003）
- fixture・テスト・ドキュメント・Issue に実際の会議の内容、予定、人名、メールアドレス、社名、案件名、個人のパスを入れない。`acme.example` のような架空の値を使う
- 整形、構造変更、挙動変更を同じ変更に混ぜない
- 一時的な作業（下書き、調査ダンプ、単発スクリプト）は `z-ai/` に置く。git 管理外
