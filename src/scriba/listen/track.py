"""常時録音のトラック: OS の既定の入力を録り続け、時が変わるたびにセッションを切り替える。"""

import json
import time
from datetime import datetime, timedelta

from scriba.config import Config
from scriba.recording import capture


class Track(capture._Track):
    """既定の入力を mic トラックとして録る。

    ストリームは開いたままにし、チャンクの境目でセッションを替える。セッションごとに開き直すと、
    その間の音声が欠け、無線のマイクは開くたびに立ち上がりを待つ。
    """

    def __init__(self, cfg: Config, now=datetime.now):
        self.cfg, self.now = cfg, now
        self.heard_at = time.monotonic()
        super().__init__(cfg, self._begin(now()), "mic", None)

    def _begin(self, started: datetime) -> str:
        """新しいセッションを作り、以後のチャンクの書き先にする。"""
        # 入力が続けて切り替わると同じ秒に開き直す。同じ ID を使うと、前のセッションのチャンクを上書きする
        while self.cfg.session_dir(started.strftime(self.cfg.session_format)).exists():
            started += timedelta(seconds=1)
        self.started = started
        self.session_id = started.strftime(self.cfg.session_format)
        session = self.cfg.session_dir(self.session_id)
        self.dir = session / "chunks"
        self.dir.mkdir(parents=True, exist_ok=True)
        (session / "transcripts").mkdir(exist_ok=True)
        meta = {
            "session_id": self.session_id,
            "started_at": started.isoformat(timespec="seconds"),
            "mode": "listen",
            "chunk_duration": self.cfg.chunk_duration,
            "model": self.cfg.model,
            "tracks": ["mic"],
        }
        (session / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        self.idx = 0
        # 書き込み中のチャンク。これより前のチャンクは完成している
        self.recording = (self.session_id, 0)
        return self.session_id

    def _callback(self, indata, frames, t, status) -> None:
        self.heard_at = time.monotonic()
        super()._callback(indata, frames, t, status)

    def _chunk_closed(self) -> None:
        # why not 無音の通知: 話していない時間が大半で、無音は経路の断絶を意味しない
        now = self.now()
        if (now.date(), now.hour) != (self.started.date(), self.started.hour):
            self._begin(now)
        else:
            self.recording = (self.session_id, self.idx)

    def close(self) -> None:
        try:
            self.stream.stop()
            self.stream.close()
        except Exception as e:  # 消えたデバイスのストリームは止められないことがある
            print(f"ストリームの停止に失敗: {e}", flush=True)
        self.q.put(None)
        self.thread.join(timeout=10)
        if self.file:
            self.file.close()
            self.file = None
