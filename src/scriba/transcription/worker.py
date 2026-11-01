"""F2 liveモード: 録音中のチャンクを検出して逐次文字起こしするワーカー。

チャンクの完成判定: 同一トラックで次のインデックスのWAVが存在する
（＝録音プロセスが次チャンクへ移った）か、停止フラグが立っている。
"""

import time

from scriba.transcription import transcriber
from scriba.config import Config
from scriba.recording.recorder import STOP_FLAG


def run(cfg: Config, session_id: str) -> None:
    session = cfg.session_dir(session_id)
    chunks_dir = session / "chunks"
    print(f"worker開始: {session_id}")

    while True:
        stopping = (session / STOP_FLAG).exists()
        for wav in transcriber.pending_chunks(cfg, session_id):
            if not stopping and not _is_complete(wav, chunks_dir):
                continue
            print(f"文字起こし: {wav.stem}", flush=True)
            try:
                entry = transcriber.transcribe_chunk(cfg, session_id, wav)
                print(f"  完了 {entry['process_time_sec']}s (rtf {entry['rtf']})", flush=True)
            except Exception as e:  # 失敗チャンクはスキップして継続
                print(f"  失敗（スキップ）: {e}", flush=True)
                continue
            transcriber.merge_session(cfg, session_id)

        if stopping:
            pending = transcriber.pending_chunks(cfg, session_id)
            if pending:
                raise RuntimeError(f"未処理 {len(pending)} チャンク。scriba transcribe {session_id} で再試行してください")
            transcriber.merge_session(cfg, session_id)
            (session / STOP_FLAG).unlink(missing_ok=True)
            print("worker終了")
            return
        time.sleep(3)


def _is_complete(wav, chunks_dir) -> bool:
    # 同一トラックで次インデックスのWAVがあれば書き込み完了とみなす
    m = transcriber.CHUNK_RE.match(wav.stem)
    if not m:
        return False
    track, idx = m.group(1), int(m.group(2))
    next_name = f"{track}_{idx + 1:03d}.wav"
    return (chunks_dir / next_name).exists()
