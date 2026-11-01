"""Haas のローカル認識。speech.cpp の固定版を検証して別プロセスで呼ぶ。"""

import hashlib
import json
import os
import platform
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

VERSION = "0.10.0"
RUNTIME_URL = (
    f"https://github.com/nyosegawa/speech.cpp/releases/download/v{VERSION}/"
    f"speech-{VERSION}-macos-arm64-metal.zip"
)
ARCHIVE_SHA256 = "4f48ac4aefe65a00e2724e94749f01f7993de6190998c49bb347662f96f7af6d"
RUNTIME_FILES = {
    "speech": "f344cf59d72b5f91f5838df68c37cae739f80ae0b4f141bc553a81ffde9547bd",
    "libspeech.4.dylib": "e3fac058886bc215cb237a6745fced4d1555263808569998a42478fc889d85b6",
}


class HaasError(Exception):
    pass


def _matches(path: Path, expected: str) -> bool:
    if not path.is_file():
        return False
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest() == expected


def prepare(base_dir: Path) -> Path:
    """実行ファイルと共有ライブラリを取得し、SHA256 が一致したものだけ返す。"""
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise HaasError("Haas は Apple Silicon の macOS で実行してください")
    root = base_dir / "models" / f"speech-{VERSION}"
    root.mkdir(parents=True, exist_ok=True)
    if all(_matches(root / name, sha) for name, sha in RUNTIME_FILES.items()):
        return root / "speech"

    try:
        with tempfile.TemporaryDirectory(dir=root) as staging:
            stage = Path(staging)
            archive = stage / "runtime.zip"
            with urllib.request.urlopen(RUNTIME_URL, timeout=60) as response, archive.open("wb") as out:
                while block := response.read(1024 * 1024):
                    out.write(block)
            if not _matches(archive, ARCHIVE_SHA256):
                raise HaasError("speech.cpp の配布物の SHA256 が一致しません")
            with zipfile.ZipFile(archive) as bundle:
                for name, sha in RUNTIME_FILES.items():
                    member = next(p for p in bundle.namelist() if p.split("/")[-1] == name)
                    target = stage / name
                    target.write_bytes(bundle.read(member))
                    if not _matches(target, sha):
                        raise HaasError(f"speech.cpp の {name} の SHA256 が一致しません")
            for name in RUNTIME_FILES:
                (stage / name).chmod(0o700 if name == "speech" else 0o600)
                os.replace(stage / name, root / name)
    except (OSError, ValueError, zipfile.BadZipFile, StopIteration) as e:
        raise HaasError("speech.cpp を準備できませんでした。接続と保存先を確認してください") from e
    return root / "speech"


def _run(base_dir: Path, *args: str) -> str:
    executable = prepare(base_dir)
    try:
        result = subprocess.run(
            [str(executable), *args], capture_output=True, text=True, check=True, timeout=900,
        )
    except (OSError, subprocess.SubprocessError) as e:
        # 上流の stderr に発話が混ざっても、通常の診断には出さない。
        raise HaasError("Haas の処理に失敗しました。scriba setup-model と設定を確認してください") from e
    return result.stdout


def setup(base_dir: Path, model: str) -> None:
    """speech.cpp のカタログが固定した重みを取得・検証する。"""
    _run(base_dir, "pull", model, "silero-vad")


def speech_intervals(base_dir: Path, wav: Path) -> list[list[float]]:
    raw = _run(
        base_dir, "vad", "silero-vad", "--format", "json",
        "--threshold", "0.35", "--speech-pad-ms", "200", "--min-speech-duration-ms", "100", str(wav),
    )
    try:
        return [[r["start"], r["end"]] for r in json.loads(raw)["regions"]]
    except (ValueError, TypeError, KeyError) as e:
        raise HaasError("Haas の発話検出結果が不正です") from e


def _with_keywords(base_dir: Path, model: str, language: str, wav: Path, words: list[str]) -> dict:
    # speech.cpp は keywords と timestamps を併用できない。発話区間の時刻を保持する。
    with tempfile.TemporaryDirectory(dir=base_dir) as staging:
        raw = _run(
            base_dir, "vad", "silero-vad", "--format", "json", "--split", staging,
            "--threshold", "0.35", "--speech-pad-ms", "200", "--min-speech-duration-ms", "100",
            "--min-silence-duration-ms", "500", "--max-speech-duration-s", "12", str(wav),
        )
        regions = json.loads(raw)["regions"]
        files = sorted(Path(staging).glob("*.wav"))
        if len(files) != len(regions):
            raise ValueError("missing speech regions")
        segments = []
        if files:
            results = _run(
                base_dir, "asr", model, "--language", language, "--format", "json", "--threads", "4",
                "--keywords", "\n".join(words), *map(str, files),
            ).splitlines()
            if len(results) != len(regions):
                raise ValueError("missing recognition results")
            for region, line in zip(regions, results):
                result = json.loads(line)
                if result["stop"] != "complete" or not isinstance(result["text"], str):
                    raise ValueError("incomplete recognition")
                segments.append({"start": region["start"], "end": region["end"], "text": result["text"]})
        return {"stop": "complete", "text": "".join(s["text"] for s in segments), "segments": segments}


def transcribe(base_dir: Path, model: str, language: str, wav: Path, words: list[str]) -> dict:
    args = [
        "asr", model, "--language", language, "--format", "json", "--timestamps",
        "--vad", "silero-vad", "--threads", "4",
        "--threshold", "0.35", "--speech-pad-ms", "200", "--min-speech-duration-ms", "100",
        "--max-speech-duration-s", "12",
    ]
    try:
        if words:
            data = _with_keywords(base_dir, model, language, wav, words)
        else:
            data = json.loads(_run(base_dir, *args, str(wav)))
        if data.get("stop") != "complete" or not isinstance(data.get("text"), str):
            raise ValueError("incomplete recognition")
        segments = data.get("segments")
        if not isinstance(segments, list) or (data["text"].strip() and not segments):
            raise ValueError("missing timestamps")
        for seg in segments:
            if not (0 <= seg["start"] <= seg["end"] and isinstance(seg["text"], str)):
                raise ValueError("invalid segment")
    except (ValueError, TypeError, KeyError, AttributeError) as e:
        raise HaasError("Haas の結果が不正です。音声を残したまま処理を中止しました") from e
    return {
        "text": data["text"], "segments": segments, "language": language, "model": model,
        "timestamp_source": "vad" if words else "asr",
    }
