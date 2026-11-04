"""F1: 録音制御。sounddeviceによる2トラック同時録音とセッション状態管理。"""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

from scriba import calendar, enrich
from scriba.recording import audio
from scriba.transcription import transcriber
from scriba.config import Config
from scriba.notify import notify

STOP_FLAG = "stopping"


class RecorderError(Exception):
    pass


def load_state(cfg: Config) -> dict | None:
    if not cfg.state_file.exists():
        return None
    state = json.loads(cfg.state_file.read_text(encoding="utf-8"))
    if not _alive(state.get("record_pid")):
        # 録音プロセスのクラッシュ等の残骸。出力デバイスを復元して掃除する
        audio.restore_output(state.get("prev_output"))
        cfg.state_file.unlink(missing_ok=True)
        return None
    return state


def start(cfg: Config, mode: str) -> str:
    if load_state(cfg):
        raise RecorderError("既に録音中です")

    if not shutil.which("ffmpeg"):
        # 録音はsounddeviceだが、mlx-whisperの音声読み込みにffmpegが必要
        raise RecorderError(
            "ffmpeg が見つかりません（Raycast等から起動した場合はPATHが通っていない可能性）"
        )

    prev_output = audio.validate_and_switch(cfg)
    # micの併録はliveかつcapture_mic=trueのときだけ
    use_mic = mode == "live" and cfg.capture_mic and audio.mic_available(cfg)
    if mode == "live" and cfg.capture_mic and not use_mic:
        print(f"警告: マイク「{cfg.device_mic}」が見つかりません。systemトラックのみで録音します")

    session_id = datetime.now().strftime(cfg.session_format)
    session = cfg.session_dir(session_id)
    chunks = session / "chunks"
    chunks.mkdir(parents=True, exist_ok=True)
    (session / "transcripts").mkdir(exist_ok=True)

    cmd = [sys.executable, "-m", "scriba", "record", session_id]
    if use_mic:
        cmd.append("--mic")
    record_log = open(session / "record.log", "w")
    record = subprocess.Popen(cmd, stdout=record_log, stderr=record_log, start_new_session=True)

    time.sleep(1.5)
    if record.poll() is not None:
        audio.restore_output(prev_output)
        log_tail = (session / "record.log").read_text(encoding="utf-8", errors="replace")[-500:]
        shutil.rmtree(session, ignore_errors=True)  # 失敗した空セッションは残さない
        raise RecorderError(f"録音プロセスの起動に失敗しました:\n{log_tail}")

    worker_pid = None
    if mode == "live":
        worker_log = open(session / "worker.log", "w")
        worker = subprocess.Popen(
            [sys.executable, "-m", "scriba", "worker", session_id],
            stdout=worker_log, stderr=worker_log, start_new_session=True,
        )
        worker_pid = worker.pid

    meta = {
        "session_id": session_id,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "chunk_duration": cfg.chunk_duration,
        "model": cfg.model,
        "tracks": ["system", "mic"] if use_mic else ["system"],
    }
    (session / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # カレンダー照合
    cal_result = enrich.try_match_on_start(cfg, session_id)
    if cal_result and cal_result["match"] == "ambiguous":
        print("複数の予定が見つかりました:")
        for i, ev in enumerate(cal_result["candidates"], 1):
            s = calendar.to_local(calendar.parse_utc(ev["start"])).strftime("%H:%M")
            e = calendar.to_local(calendar.parse_utc(ev["end"])).strftime("%H:%M")
            print(f"  {i}. {ev['subject']} ({s}-{e})")
        print("後から scriba title で設定してください")
    elif cal_result and cal_result["match"] == "exact":
        print(f"会議: {cal_result['event']['subject']}")

    cfg.state_file.write_text(json.dumps({
        "session_id": session_id,
        "mode": mode,
        "record_pid": record.pid,
        "worker_pid": worker_pid,
        "prev_output": prev_output,
        "started_at": meta["started_at"],
    }, ensure_ascii=False), encoding="utf-8")

    notify("Scriba", f"録音開始（{mode}）: {session_id}")
    return session_id


def stop(cfg: Config, only_session: str | None = None) -> str:
    state = load_state(cfg)
    if not state:
        raise RecorderError("録音していません")
    session_id = state["session_id"]
    if only_session and session_id != only_session:
        raise RecorderError(f"録音中のセッションが {only_session} ではないため停止しません")
    session = cfg.session_dir(session_id)

    # SIGINTで録音プロセスに書き込み中チャンクを確定させる
    _terminate(state["record_pid"], sig=signal.SIGINT)
    audio.restore_output(state.get("prev_output"))

    unsaved = _unsaved_reason(cfg, state, session)
    if unsaved:
        notice, error = unsaved
        _terminate(state.get("worker_pid"))
        shutil.rmtree(session, ignore_errors=True)
        _release_state(cfg, session_id)
        notify("Scriba", notice)
        raise RecorderError(error)

    reason = _consume_stop_reason(session)
    timed_out = reason == "timeout"

    # meta更新
    meta_file = session / "meta.json"
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    meta["stopped_at"] = datetime.now().isoformat(timespec="seconds")
    if reason:
        meta["stopped_reason"] = reason
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # 録音は止まったのでstateをここで解放する。
    # 以降の文字起こし・enrichは長時間かかりうる後処理で、その間に新しい録音を
    # 開始してよい。末尾で解放すると新セッションのstateを消す事故になる
    # （2026-07-17: 長いstop中のstartで発生、録音プロセスが孤児化した）
    _release_state(cfg, session_id)

    if state["mode"] == "live":
        # ワーカーに停止を通知し、残チャンクの処理完了を待つ
        (session / STOP_FLAG).touch()
        notify("Scriba", "録音停止（残りを文字起こし中...）")
        _wait_pid(state.get("worker_pid"), timeout=600)
        if transcriber.pending_chunks(cfg, session_id):
            notify("Scriba", "未処理の音声があります。文字起こしを再試行してください")
            raise RecorderError(f"未処理の音声があります。scriba transcribe {session_id} で再試行してください")
        notify("Scriba", "文字起こし完了")
    else:
        notify("Scriba", "録音停止")
        if cfg.transcribe_on_stop:
            print("バッチ文字起こしを開始...")
            transcriber.transcribe_session(cfg, session_id)
            notify("Scriba", "文字起こし完了")

    if timed_out:
        print("タイムアウト停止のため enrich/export をスキップしました。確認してから scriba enrich / scriba export を実行してください。")
    else:
        # enrich: frontmatter付きに更新
        enrich_result = enrich.enrich_session(cfg, session_id)
        if enrich_result and enrich_result.get("path"):
            print(f"enrich: {enrich_result['path']}")

        # auto export（title+enrich確定時のみ）
        meta = json.loads((session / "meta.json").read_text(encoding="utf-8"))
        if meta.get("title") and meta.get("enrich"):
            from scriba import export as _export
            ex_result = _export.export_session(cfg, session_id)
            if ex_result and not ex_result.get("skipped"):
                print(f"export: {ex_result['path']}")

    from scriba import export as _export
    _export.notify_unexported(cfg)

    return session_id


def status(cfg: Config) -> dict | None:
    state = load_state(cfg)
    if not state:
        return None
    session = cfg.session_dir(state["session_id"])
    started = datetime.fromisoformat(state["started_at"])
    n_chunks = transcriber.count_system(session / "chunks", ".wav")
    n_done = transcriber.count_system(session / "transcripts", ".json")
    return {
        **state,
        "elapsed_sec": int((datetime.now() - started).total_seconds()),
        "chunks": n_chunks,
        "transcribed": n_done,
    }


def discard(cfg: Config, session_id: str | None = None) -> str:
    """セッションを丸ごと削除する。録音中なら止めてから破棄。IDなしなら最新を対象。"""
    state = load_state(cfg)
    if state and (session_id is None or session_id == state["session_id"]):
        # 録音中セッションの破棄: 録音プロセス/workerを止めて消す
        sid = state["session_id"]
        _terminate(state["record_pid"], sig=signal.SIGINT)
        _terminate(state.get("worker_pid"))
        audio.restore_output(state.get("prev_output"))
        cfg.state_file.unlink(missing_ok=True)
        shutil.rmtree(cfg.session_dir(sid), ignore_errors=True)
        notify("Scriba", f"録音を中止して破棄: {sid}")
        return sid

    if session_id is None:
        sessions = sorted(p.name for p in cfg.sessions_dir.iterdir() if p.is_dir()) if cfg.sessions_dir.exists() else []
        if not sessions:
            raise RecorderError("セッションがありません")
        session_id = sessions[-1]

    target = cfg.session_dir(session_id)
    if not target.exists():
        raise RecorderError(f"セッションが見つかりません: {session_id}")
    shutil.rmtree(target)
    return session_id


def cleanup(cfg: Config) -> list[str]:
    """retention_daysを超えたセッションのWAV（またはセッション丸ごと）を削除。"""
    removed = []
    if not cfg.sessions_dir.exists():
        return removed
    now = time.time()
    limit = cfg.retention_days * 86400
    state = load_state(cfg)
    active = state["session_id"] if state else None

    for session in cfg.sessions_dir.iterdir():
        if not session.is_dir() or session.name == active:
            continue
        if now - session.stat().st_mtime < limit:
            continue
        if transcriber.pending_chunks(cfg, session.name):
            # 未文字起こしのWAVは消さない（音声が失われるため）
            print(f"スキップ（未文字起こし）: {session.name} — scriba transcribe {session.name} で処理してください")
            continue
        if cfg.cleanup_target == "all":
            shutil.rmtree(session)
            removed.append(f"{session.name} (all)")
        else:
            wavs = list((session / "chunks").glob("*.wav"))
            for w in wavs:
                w.unlink()
            if wavs:
                removed.append(f"{session.name} ({len(wavs)} wav)")
    return removed


def _alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _release_state(cfg: Config, session_id: str) -> None:
    """stateが自分のセッションのときだけ消す。

    自動停止と手動停止が重なると、先に終わった側の後に新しい録音が始まりうる。
    後から来た側が新しいセッションのstateを消さないようにする。
    """
    try:
        current = json.loads(cfg.state_file.read_text(encoding="utf-8")).get("session_id")
    except (OSError, ValueError):
        return
    if current == session_id:
        cfg.state_file.unlink(missing_ok=True)


def _unsaved_reason(cfg: Config, state: dict, session: Path) -> tuple[str, str] | None:
    """保存せずに破棄するセッションなら、その（通知, エラー）の文言。"""
    if not list((session / "chunks").glob("*.wav")):
        return "音声が録音できませんでした（セッション破棄）", "音声が録音できませんでした。セッションを破棄しました"
    # 待機画面だけや、誤って入った会議の録音
    recorded_sec = (_ended_at(session) - datetime.fromisoformat(state["started_at"])).total_seconds()
    if recorded_sec < cfg.min_keep_sec:
        return f"{cfg.min_keep_sec}秒未満の録音のため破棄しました", f"{cfg.min_keep_sec}秒未満の録音のため、セッションを破棄しました"
    return None


def _ended_at(session: Path) -> datetime:
    """会議の終了で止めたなら watch が書いた終了時刻、それ以外は今。"""
    try:
        return datetime.fromisoformat((session / "meeting_end").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # 印がない、または終了時刻を書かない旧版の空の印
        return datetime.now()


def _consume_stop_reason(session: Path) -> str | None:
    """録音プロセスと watch が残した停止理由のフラグ（meeting_end / autostop / timeout）を読んで消す。"""
    reason = None
    for flag, name in (("meeting_end", "meeting_end"), ("autostop", "silence"), ("timeout", "timeout")):
        if (session / flag).exists():
            (session / flag).unlink()
            reason = name  # 両方あれば timeout を優先（enrich/export をスキップさせる）
    return reason


def _terminate(pid: int | None, sig=signal.SIGTERM, timeout: float = 10.0) -> None:
    if not _alive(pid):
        return
    os.kill(pid, sig)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _alive(pid):
            return
        time.sleep(0.2)
    os.kill(pid, signal.SIGKILL)


def _wait_pid(pid: int | None, timeout: float) -> None:
    deadline = time.time() + timeout
    while _alive(pid) and time.time() < deadline:
        time.sleep(1)
