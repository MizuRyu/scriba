"""常時録音の文字起こし待ち: 完成したチャンクを 1 つずつ処理し、発話の無い音声とセッションを残さない。"""

import json
import shutil
from pathlib import Path

from scriba.config import Config
from scriba.transcription import transcriber


class Backlog:
    """文字起こしを待つセッションの列。

    起動時は残っている全セッション（前回の取りこぼし）を持ち、以後は録音中のセッションだけが足される。
    処理を終えたセッションは列から外すので、過去のセッションを毎回走査しない。
    """

    def __init__(self, cfg: Config, transcribe=transcriber.transcribe_chunk, merge=transcriber.merge_session):
        self.cfg, self.transcribe, self.merge = cfg, transcribe, merge
        root = cfg.sessions_dir
        self.sessions = sorted(p.name for p in root.iterdir() if p.is_dir()) if root.exists() else []
        self.failed: set[Path] = set()

    def add(self, session_id: str) -> None:
        if session_id not in self.sessions:
            self.sessions.append(session_id)

    def step(self, recording: tuple[str, int] | None, busy: bool) -> bool:
        """完成したチャンクを 1 つ文字起こしする。処理したら True。

        recording は書き込み中のチャンク（セッション、番号）。busy の間は文字起こしを始めない。
        """
        for session_id in list(self.sessions):
            wav = self._next(session_id, recording)
            if wav:
                if busy:
                    return False
                self._transcribe(session_id, wav)
                return True
            if not recording or session_id != recording[0]:
                self._finish(session_id)
        return False

    def _next(self, session_id: str, recording: tuple[str, int] | None) -> Path | None:
        for wav in transcriber.pending_chunks(self.cfg, session_id):
            idx = int(transcriber.CHUNK_RE.match(wav.stem).group(2))
            if wav not in self.failed and (session_id, idx) != recording:
                return wav
        return None

    def _transcribe(self, session_id: str, wav: Path) -> None:
        try:
            entry = self.transcribe(self.cfg, session_id, wav)
        except Exception as e:  # 失敗したチャンクで常駐を止めない。音声は残り、次の起動で再試行する
            print(f"文字起こし失敗（次の起動で再試行）: {session_id}/{wav.stem}: {e}", flush=True)
            self.failed.add(wav)
            return
        if entry["no_speech_skipped"]:
            wav.unlink()
        else:
            self.merge(self.cfg, session_id)
        print(f"処理: {session_id}/{wav.stem} speech={not entry['no_speech_skipped']}", flush=True)

    def _finish(self, session_id: str) -> None:
        """録音を終えたセッションを列から外す。発話が 1 つも無ければセッションごと消す。"""
        self.sessions.remove(session_id)
        session = self.cfg.session_dir(session_id)
        if not transcriber.pending_chunks(self.cfg, session_id) and not _has_text(session):
            shutil.rmtree(session, ignore_errors=True)


def _has_text(session: Path) -> bool:
    for chunk in (session / "transcripts").glob("*.json"):
        if transcriber.CHUNK_RE.match(chunk.stem) and json.loads(chunk.read_text(encoding="utf-8")).get("text", "").strip():
            return True
    return False
