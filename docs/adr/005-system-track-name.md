# ADR-005 相手側のトラックを system と呼ぶ

- 状態: 承認
- 日付: 2026-11-01
- 関連: [03 Features](../specs/03-features.md) F1・F11、`src/scriba/transcription/transcriber.py`

## 文脈

相手の声を録るトラックは、Teams 専用に作った経緯から `teams` と呼んでいた。チャンクのファイル名（`teams_000.wav`）、meta.json の `tracks`、CLI の `--track teams`、ビューアのトラックフィルタまで、この名前が通っている。実際に録っているのは会議アプリを問わないシステム音声（BlackHole）で、Zoom などでも同じ。

## 決定

- 新しく録るトラックは `system` と `mic` にする
- 旧名 `teams` は読むときに `system` に読み替える（`canonical_track`）。マージ、トラックフィルタ、チャンク数の表示、`--track teams` のいずれも両方の名前で同じ結果になる
- 既存セッションのファイル名や meta.json は書き換えない

## 見直し条件

- 旧名のセッションが手元からすべてなくなったとき、読み替えを外せる。確認: `fd 'teams_\d{3}' "${SCRIBA_HOME:-~/scriba}/sessions"` が何も出さない
