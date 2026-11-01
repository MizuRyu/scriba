"""F9: transcript の転送。

案件判定済み → {export_dir}/{export_subdir} にコピー（既定 transcript/{project}/）
未分類 → exportしない（ユーザーが手動で分類してからexport）
export_dir が未設定なら転送も未転送の数え上げもしない
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

from scriba import classify
from scriba.config import Config
from scriba.notify import notify


def export_session(cfg: Config, session_id: str, project_override: str | None = None) -> dict | None:
    session = cfg.session_dir(session_id)
    meta_file = session / "meta.json"
    if not meta_file.exists():
        return None
    if not cfg.export_dir:
        return {"skipped": True, "reason": "export_dir not set"}

    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    if meta.get("exported_at"):
        return {"skipped": True, "reason": "already exported"}

    from scriba.transcription import transcriber

    combined = transcriber.find_combined(cfg, session_id)
    if not combined:
        return {"skipped": True, "reason": "no combined file"}

    project = project_override or _classify(cfg, meta)
    if not project:
        return {"skipped": True, "reason": "unclassified"}

    dest_dir = Path(cfg.export_dir).expanduser() / cfg.export_subdir.format(project=project)

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / combined.name
    shutil.copy2(combined, dest_path)

    meta["exported_at"] = datetime.now().isoformat(timespec="seconds")
    meta["exported_to"] = str(dest_path)
    meta["project"] = project
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # 仕訳ルールを記録
    title = meta.get("title", "")
    if title and project:
        classify.record_rule(cfg, title, project)

    return {"path": str(dest_path), "project": project}


def _classify(cfg: Config, meta: dict) -> str | None:
    enrich_data = meta.get("enrich")
    if not enrich_data:
        return None
    from scriba import enrich
    return enrich.build_enrich_meta(enrich_data, cfg).get("project")


def list_unexported(cfg: Config) -> list[dict]:
    """combined があるのに未転送のセッションを古い順に返す。"""
    if not cfg.export_dir or not cfg.sessions_dir.exists():
        return []
    from scriba.transcription import transcriber

    active = None
    if cfg.state_file.exists():
        # 録音中のセッションは live ワーカーが combined を逐次書くので数えない
        active = json.loads(cfg.state_file.read_text(encoding="utf-8")).get("session_id")
    out = []
    for meta_file in sorted(cfg.sessions_dir.glob("*/meta.json")):
        sid = meta_file.parent.name
        if sid == active:
            continue
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        if meta.get("exported_at") or not transcriber.find_combined(cfg, sid):
            continue
        out.append({
            "id": sid,
            "title": meta.get("title", ""),
            "started_at": meta.get("started_at", ""),
            "reason": "not exported" if _classify(cfg, meta) else "unclassified",
        })
    return out


def notify_unexported(cfg: Config) -> None:
    unexported = list_unexported(cfg)
    if not unexported:
        return
    msg = f"未転送 {len(unexported)} 件（scriba export {unexported[-1]['id']} --project <案件>）"
    notify("Scriba", msg)
    print(msg)
