"""F8: 会議の組織・案件の推定と、export 時に学習する仕訳ルール。

案件の評価順: 1. 仕訳ルール（{base_dir}/classification_rules.jsonl）→ 2. config.toml のキーワード（定義順、先勝ち）
"""

import json
import re
from datetime import datetime
from pathlib import Path

from scriba.config import Config


def organization(organizer: str, orgs: dict[str, str]) -> str | None:
    """organizer メールアドレスのドメインから組織名を推定。"""
    if not organizer or "@" not in organizer:
        return None
    domain = organizer.split("@", 1)[1].lower()
    if domain in orgs:
        return orgs[domain]
    # サブドメイン照合: sales.example.com → example.com
    parts = domain.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[i:])
        if parent in orgs:
            return orgs[parent]
    return domain


def project(subject: str, projects: list[dict], rules: dict[str, str] | None = None) -> str | None:
    """subject から案件の alias を推定。"""
    if not subject:
        return None
    if rules:
        normalized = normalize_title(subject)
        if normalized in rules:
            return rules[normalized]
    for proj in projects:
        for kw in proj.get("keywords", []):
            if kw in subject:
                return proj["alias"]
    return None


def normalize_title(title: str) -> str:
    """タイトルを正規化（日付・回数等を除去して定例判定可能にする）。"""
    s = title.strip()
    s = re.sub(r'\d{4}[/-]\d{1,2}[/-]\d{1,2}', '', s)
    s = re.sub(r'\d{1,2}/\d{1,2}', '', s)
    s = re.sub(r'第\d+回', '', s)
    s = re.sub(r'_\d{4}$', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def load_rules(cfg: Config) -> dict[str, str]:
    """保存済み仕訳ルールを {normalized_title: project} で返す。"""
    rules_file = _rules_file(cfg)
    if not rules_file.exists():
        return {}
    rules = {}
    for line in rules_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        rules[entry["title_normalized"]] = entry["project"]
    return rules


def record_rule(cfg: Config, title: str, project: str) -> None:
    """仕訳ルールを記録。同じタイトルの定例は次回から自動分類。"""
    normalized = normalize_title(title)

    existing = load_rules(cfg)
    if normalized in existing and existing[normalized] == project:
        return

    with open(_rules_file(cfg), "a", encoding="utf-8") as f:
        entry = json.dumps({
            "title_normalized": normalized,
            "title_original": title,
            "project": project,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }, ensure_ascii=False)
        f.write(entry + "\n")


def _rules_file(cfg: Config) -> Path:
    return cfg.base_dir / "classification_rules.jsonl"
