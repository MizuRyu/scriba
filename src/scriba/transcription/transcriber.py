"""文字起こし: Haas / mlx-whisper 呼び出し、2トラックのマージ、パフォーマンスログ。"""

import json
import os
import re
import subprocess
import time
import wave
from datetime import datetime
from pathlib import Path

from scriba.transcription import dictionary, haas, vad
from scriba.config import Config

TRACK_LABELS = {"system": "[相手]", "mic": "[自分]"}
# 旧バージョンは system トラックを teams と呼んでいた。読むときは system として扱う
LEGACY_TRACKS = {"teams": "system"}
SYSTEM_GLOBS = ("system_*", "teams_*")
CHUNK_RE = re.compile(r"^(system|teams|mic)_(\d{3})$")
_FILENAME_BAD = re.compile(r'[/\\:*?"<>|]')
_REPEAT_PATTERN = re.compile(r'(.{2,50}?)\1{2,}')


def _trim_repeated_phrases(text: str) -> str:
    """同一フレーズの異常連続（Whisper幻聴）を最初の1回だけに圧縮。"""
    return _REPEAT_PATTERN.sub(r'\1', text)


def combined_filename(cfg: Config, session_id: str) -> str:
    """combined の出力ファイル名を返す。

    meta.json の started_at から ``yymmdd_hhmm`` を生成し、title があれば
    ``yymmdd_hhmm_タイトル.txt``、なければ ``yymmdd_hhmm.txt``。
    started_at がなければ session_id の先頭12文字をフォールバックに使う。
    """
    meta_file = cfg.session_dir(session_id) / "meta.json"
    meta: dict = {}
    if meta_file.exists():
        meta = json.loads(meta_file.read_text(encoding="utf-8"))

    started = meta.get("started_at")
    if started:
        try:
            dt = datetime.fromisoformat(started)
            stem = dt.strftime("%y%m%d_%H%M")
        except ValueError:
            stem = session_id[:12]
    else:
        stem = session_id[:12]

    title = meta.get("title", "")
    if title:
        safe = _FILENAME_BAD.sub("-", title)
        return f"{stem}_{safe}.txt"
    return f"{stem}.txt"


def find_combined(cfg: Config, session_id: str) -> Path | None:
    """transcripts/ 内の combined ファイルを探して返す。

    .txt のうちチャンク JSON と同 stem でないものを combined とみなす。
    0件なら None、複数あれば最新の mtime を返す。
    """
    out_dir = cfg.session_dir(session_id) / "transcripts"
    if not out_dir.exists():
        return None
    json_stems = {p.stem for p in out_dir.glob("*.json")}
    candidates = [p for p in out_dir.glob("*.txt") if p.stem not in json_stems]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def transcribe_chunk(cfg: Config, session_id: str, wav: Path) -> dict:
    """1チャンクを文字起こしし、perfログ用のエントリを返す。"""
    out_dir = cfg.session_dir(session_id) / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)

    dic = dictionary.load(cfg.dictionary_path)
    prompt = dic.build_prompt(cfg.model)
    verdict, _ = dictionary.validate_prompt(prompt, cfg.model)
    if verdict == "block":
        prompt = ""  # 上限超過の辞書は使わない（録音を止めないことを優先）

    cmd = [
        "uvx", "--from", "mlx-whisper", "mlx_whisper", str(wav),
        "--model", cfg.model,
        "--language", cfg.language,
        "--task", "transcribe",
        "--output-dir", str(out_dir),
        "--output-format", "json",
        "--verbose", "False",
        # 120秒チャンク末尾のループ（同一文の繰り返し）対策
        "--condition-on-previous-text", "False",
    ]
    if prompt:
        cmd += ["--initial-prompt", prompt]

    t0 = time.time()
    speech = _has_speech(wav, out_dir, cfg)
    if speech and cfg.model.startswith("haas-"):
        words = [t["word"] for t in dic.terms if t.get("priority") == "high"]
        data = haas.transcribe(cfg.base_dir, cfg.model, cfg.language, wav, words)
        result = out_dir / f"{wav.stem}.json"
        tmp = result.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, result)
    elif speech:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    else:
        # 発話のないmicチャンクはWhisperに通さない（幻聴しか出ず、GPUも使う）
        empty = {"text": "", "segments": [], "language": cfg.language}
        (out_dir / f"{wav.stem}.json").write_text(json.dumps(empty), encoding="utf-8")
    elapsed = time.time() - t0

    audio_sec = _wav_duration(wav)
    result_json = out_dir / f"{wav.stem}.json"
    text_length = 0
    if result_json.exists():
        data = json.loads(result_json.read_text(encoding="utf-8"))
        text_length = len(data.get("text", ""))

    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "session": session_id,
        "chunk": wav.stem,
        "audio_duration_sec": round(audio_sec, 1),
        "process_time_sec": round(elapsed, 1),
        "rtf": round(elapsed / audio_sec, 3) if audio_sec else None,
        "model": cfg.model,
        "text_length": text_length,
        "no_speech_skipped": not speech,
    }
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    with open(cfg.perf_log, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def merge_session(cfg: Config, session_id: str, until_sec: float | None = None, only_tracks: set[str] | None = None) -> Path:
    """system/micトラックのJSONをタイムスタンプで時刻順にマージし combined ファイルを生成。

    combined は「フィルタ・置換辞書を適用済みの正データ」1本のみとする。
    raw（無加工）の別ファイルは作らない。生データはチャンクごとの
    transcripts/*.json が既に担っており、combined はそこからいつでも再生成できる
    （辞書を育てた後の再適用や、幻聴定型の除去はこの再生成で反映する）。

    until_sec を指定すると、その秒数以降に開始するセグメントを除外する
    （会議より長く録ってしまったときの末尾切り落とし用）。
    """
    out_dir = cfg.session_dir(session_id) / "transcripts"
    dic = dictionary.load(cfg.dictionary_path)
    if only_tracks:
        only_tracks = {canonical_track(t) for t in only_tracks}

    segments = []  # (global_start, track, chunk_idx, text)
    tracks = set()
    filtered = 0
    for json_file in sorted(out_dir.glob("*.json")):
        m = CHUNK_RE.match(json_file.stem)
        if not m:
            continue
        track, idx = canonical_track(m.group(1)), int(m.group(2))
        if only_tracks and track not in only_tracks:
            continue
        tracks.add(track)
        offset = idx * cfg.chunk_duration
        for seg in _chunk_segments(json_file):
            text = seg.get("text", "").strip()
            if not text:
                continue
            start = offset + seg["start"]
            if until_sec is not None and start >= until_sec:
                continue
            # 置換辞書の適用より前に、幻聴定型・単独相槌のセグメントを除去
            if cfg.filters_enabled and dic.is_filtered(text):
                filtered += 1
                continue
            segments.append((start, track, idx, text))
    segments.sort(key=lambda s: s[0])
    if filtered:
        print(f"フィルタ除去: {filtered}セグメント")

    # 正規化後テキストが直前と同一の連続セグメントを畳む（トラックをまたいでも畳む）。
    # 2トラックのエコーやWhisperの繰り返しで生じる同一発話の連続を除去する。
    deduped = []
    prev_norm = None
    collapsed = 0
    for seg in segments:
        norm = dictionary.normalize_filter(seg[3])
        if norm and norm == prev_norm:
            collapsed += 1
            continue
        deduped.append(seg)
        prev_norm = norm
    segments = deduped
    if collapsed:
        print(f"重複畳み込み: {collapsed}セグメント")

    # 単一トラック（systemのみ）なら話者ラベルは付けず時刻見出しのみ
    multi = len(tracks) > 1

    lines = []
    current = None  # multi: 直前の話者ラベル / single: 直前のチャンク番号
    for start, track, idx, text in segments:
        text = dic.apply_replacements(text)
        text = _trim_repeated_phrases(text)
        # multi: 話者交代で見出し。single: チャンク境界（各チャンク最初のセグメント）で見出し
        if multi:
            speaker = TRACK_LABELS[track]
            marker = speaker
            heading = f"{_fmt_time(start)} {speaker}"
        else:
            marker = idx
            heading = _fmt_time(start)
        if marker != current:
            current = marker
            lines.append("")
            lines.append(heading)
        lines.append(text)

    # enrich が付けた frontmatter は本文の再生成で失わないよう引き継ぐ
    frontmatter = _existing_frontmatter(cfg, session_id)

    fname = combined_filename(cfg, session_id)
    combined = out_dir / fname
    combined.write_text(frontmatter + "\n".join(lines).lstrip() + "\n", encoding="utf-8")

    # 旧ファイルの掃除: .txt のうちチャンク JSON と同 stem でないものが旧 combined
    json_stems = {p.stem for p in out_dir.glob("*.json")}
    for old in out_dir.glob("*.txt"):
        if old.stem not in json_stems and old != combined:
            old.unlink()

    return combined


def canonical_track(name: str) -> str:
    return LEGACY_TRACKS.get(name, name)


def count_system(directory: Path, suffix: str) -> int:
    """system トラックのファイル数（旧名 teams_* も数える）。"""
    return sum(len(list(directory.glob(g + suffix))) for g in SYSTEM_GLOBS)


def _has_speech(wav: Path, out_dir: Path, cfg: Config) -> bool:
    """micチャンクの発話区間を求めて保存し、発話があるかを返す。systemは常にTrue。"""
    if not wav.stem.startswith("mic_"):
        return True
    try:
        if cfg.model.startswith("haas-"):
            intervals = haas.speech_intervals(cfg.base_dir, wav)
        else:
            intervals = vad.speech_intervals(wav)
    except (haas.HaasError, subprocess.CalledProcessError, OSError, ValueError) as e:
        # VADが使えなくても文字起こしは止めない（フィルタだけで守る）
        print(f"  VAD失敗（区間なしで続行）: {e}", flush=True)
        return True
    # 録音プロセスの自動停止判定が並行して読むので、書き込み途中を見せない
    path = vad.vad_path(out_dir / f"{wav.stem}.json")
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(intervals), encoding="utf-8")
    os.replace(tmp, path)
    return bool(intervals)


def _chunk_segments(json_file: Path) -> list[dict]:
    """チャンクJSONのセグメント。VAD結果があれば発話区間と重なるものだけ。"""
    segments = json.loads(json_file.read_text(encoding="utf-8")).get("segments", [])
    vad_file = vad.vad_path(json_file)
    if not vad_file.exists():
        return segments
    intervals = json.loads(vad_file.read_text(encoding="utf-8"))
    return [s for s in segments if vad.overlaps(s, intervals)]


def _existing_frontmatter(cfg: Config, session_id: str) -> str:
    """既存 combined 先頭の frontmatter（区切り後の空行込み）。なければ空文字。"""
    combined = find_combined(cfg, session_id)
    if not combined:
        return ""
    text = combined.read_text(encoding="utf-8")
    end = text.find("\n---\n", 4) if text.startswith("---\n") else -1
    return text[:end + 5] + "\n" if end != -1 else ""


def pending_chunks(cfg: Config, session_id: str) -> list[Path]:
    """未文字起こしのチャンク（transcripts/に対応JSONがないWAV）を返す。"""
    session = cfg.session_dir(session_id)
    out_dir = session / "transcripts"
    done = {p.stem for p in out_dir.glob("*.json")} if out_dir.exists() else set()
    wavs = sorted((session / "chunks").glob("*.wav"))
    return [w for w in wavs if w.stem not in done and CHUNK_RE.match(w.stem)]


def transcribe_session(cfg: Config, session_id: str, log=print) -> int:
    """セッションの未処理チャンクを一括文字起こし。処理件数を返す。"""
    chunks = pending_chunks(cfg, session_id)
    for wav in chunks:
        log(f"文字起こし: {wav.stem}")
        entry = transcribe_chunk(cfg, session_id, wav)
        log(f"  完了 {entry['process_time_sec']}s (rtf {entry['rtf']})")
    if chunks:
        combined = merge_session(cfg, session_id)
        log(f"combined 更新: {combined}")
    return len(chunks)


def _wav_duration(wav: Path) -> float:
    try:
        with wave.open(str(wav)) as w:
            return w.getnframes() / w.getframerate()
    except Exception:
        return 0.0


def _fmt_time(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"[{h}:{m:02d}:{s:02d}]" if h else f"[{m:02d}:{s:02d}]"
