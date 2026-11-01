"""F8: カレンダー照合・メタ情報付加。

録音開始時刻に最も近い予定を照合し、会議名・組織・案件を frontmatter として付ける。
予定の取得元は scriba.calendar のアダプタ。
"""

import json
from datetime import datetime
from pathlib import Path

from scriba import calendar, classify
from scriba.config import Config

MATCH_THRESHOLD_SEC = 600  # ±10分


def match_event(events: list[dict], start_time: datetime) -> dict:
    """start_time に最も近い予定を返す。

    Returns:
        {"match": "exact", "event": {...}}
        {"match": "ambiguous", "candidates": [{...}, ...]}
        {"match": "none", "candidates": []}
    """
    start_time = start_time.astimezone()

    candidates = []
    for ev in events:
        ev_start = calendar.parse_utc(ev.get("start", ""))
        diff = abs((ev_start - start_time).total_seconds())
        if diff <= MATCH_THRESHOLD_SEC:
            candidates.append({
                "event": ev,
                "diff_sec": diff,
                "start_utc": ev_start,
            })

    if not candidates:
        return {"match": "none", "candidates": []}

    candidates.sort(key=lambda c: c["diff_sec"])
    best = candidates[0]

    # 同一開始時刻で複数あるか
    same_start = [c for c in candidates if c["start_utc"] == best["start_utc"]]
    if len(same_start) > 1:
        return {
            "match": "ambiguous",
            "candidates": [c["event"] for c in same_start],
        }

    return {"match": "exact", "event": best["event"]}


def build_enrich_meta(event: dict, cfg: Config) -> dict:
    """マッチしたイベントからenrich用メタ情報を構築。"""
    subject = event.get("subject", "")
    organizer = event.get("organizer", "")
    start = calendar.to_local(calendar.parse_utc(event.get("start", "")))
    end = calendar.to_local(calendar.parse_utc(event.get("end", "")))
    rules = classify.load_rules(cfg)

    return {
        "title": subject,
        "date": start.strftime("%Y-%m-%d"),
        "start": start.strftime("%H:%M"),
        "end": end.strftime("%H:%M"),
        "organization": classify.organization(organizer, cfg.enrich_organizations),
        "project": classify.project(subject, cfg.enrich_projects, rules),
    }


def generate_frontmatter(meta: dict, session_id: str) -> str:
    """frontmatter YAML文字列を生成。"""
    fm = {
        "title": meta.get("title", ""),
        "date": meta.get("date", ""),
        "start": meta.get("start", ""),
        "end": meta.get("end", ""),
        "organization": meta.get("organization"),
        "project": meta.get("project"),
        "source_session": session_id,
    }
    lines = ["---"]
    for k, v in fm.items():
        if v is None:
            lines.append(f"{k}: null")
        elif isinstance(v, str) and ('"' in v or ":" in v or v == ""):
            lines.append(f'{k}: "{v}"')
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def enrich_session(cfg: Config, session_id: str) -> dict | None:
    """セッションのmeta.jsonにenrich情報を書き込み、frontmatter付きcombinedを生成。"""
    session = cfg.session_dir(session_id)
    meta_file = session / "meta.json"
    if not meta_file.exists():
        return None

    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    enrich = meta.get("enrich")
    if not enrich:
        return None

    fm_meta = build_enrich_meta(enrich, cfg)
    fm_meta["title"] = meta.get("title") or fm_meta["title"]

    frontmatter = generate_frontmatter(fm_meta, session_id)

    # combined の先頭に frontmatter を付加（既存があれば差し替え）
    from scriba.transcription import transcriber

    combined = transcriber.find_combined(cfg, session_id) or _legacy_combined(session)
    if combined:
        body = combined.read_text(encoding="utf-8")
        if body.startswith("---\n"):
            end = body.find("\n---\n", 4)
            if end != -1:
                body = body[end + 5:].lstrip("\n")
        combined.write_text(frontmatter + "\n" + body, encoding="utf-8")

        # titleに合わせてファイル名を更新
        new_name = transcriber.combined_filename(cfg, session_id)
        new_path = combined.parent / new_name
        if combined != new_path:
            combined.rename(new_path)
            combined = new_path

        return {"frontmatter": fm_meta, "path": str(combined)}

    return {"frontmatter": fm_meta, "path": None}


def try_match_on_start(cfg: Config, session_id: str) -> dict | None:
    """scriba start 時に呼ばれる。calendar照合してmeta.jsonに書き込む。"""
    now = datetime.now().astimezone()
    events = calendar.load_events(cfg, now)
    if not events:
        return None

    result = match_event(events, now)

    if result["match"] == "exact":
        event = result["event"]
        meta_file = cfg.session_dir(session_id) / "meta.json"
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        meta["enrich"] = event
        meta["title"] = event.get("subject", "")
        meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    if result["match"] == "ambiguous":
        return result

    return None


def _legacy_combined(session: Path) -> Path | None:
    """初期のバージョンがセッション直下に書いた combined*.txt。"""
    candidates = sorted(session.glob("combined*.txt"))
    return candidates[0] if candidates else None
