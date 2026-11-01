import json
from pathlib import Path

import pytest

from scriba.config import Config


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(base_dir=tmp_path)


def write_transcript(session_dir: Path, chunk: str, segments: list[dict], text: str = "") -> None:
    """偽の Whisper JSON をセッションの transcripts/ に置く。"""
    out_dir = session_dir / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"text": text, "segments": segments}
    (out_dir / f"{chunk}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
