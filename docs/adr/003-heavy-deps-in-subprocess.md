# ADR-003 重い依存は別プロセスで呼ぶ

- 状態: 承認
- 日付: 2026-10-23
- 関連: [07 プロジェクト構成](../specs/07-project-structure.md)、`src/scriba/transcription/transcriber.py`、`src/scriba/transcription/vad.py`

## 文脈

mlx-whisper は MLX を、Silero VAD は torch を引き込む。どちらも大きく、scriba 本体（CLI、録音、ビューア）の起動や `uv tool install` を重くする。モデルのロードはチャンクごとに 2〜3 秒かかるが、120 秒チャンクに対しては許容できる。

## 決定

- mlx-whisper は `uvx --from mlx-whisper mlx_whisper` で、Silero VAD は `uv run --no-project --with silero-vad` で、チャンクごとに別プロセスとして呼ぶ
- scriba 本体の依存（`pyproject.toml`）には入れない。実行には `uv` が要る
- VAD が失敗しても文字起こしは止めない（フィルタだけで幻聴を抑える）

## 却下した案

- **モデルを常駐させるワーカー**: ロード時間は消えるが、メモリを占有し続け、プロセス管理が増える。チャンク長に対してロード時間が小さいので見送った

## 見直し条件

- チャンク長を短くして、ロード時間が処理時間の大半を占めるようになったとき
- `uv` を前提にできない配布形態（単体の .app など）にするとき
