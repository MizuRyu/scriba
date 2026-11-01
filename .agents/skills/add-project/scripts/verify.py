#!/usr/bin/env python3
"""プロジェクト設定の検証: 定義一覧・キーワード重複・学習済みルール競合・サンプルタイトル判定。

使い方（scribaリポジトリのルートで）:
  uv run python .agents/skills/add-project/scripts/verify.py "会議タイトル1" "会議タイトル2"

終了コード: キーワード重複があれば1、なければ0
"""
import sys

from scriba import classify, config


def main():
    cfg = config.load()
    print("== enrich.projects（評価順） ==")
    for i, p in enumerate(cfg.enrich_projects, 1):
        print(f"  {i}. {p['alias']}: {', '.join(p.get('keywords', []))}")

    # キーワード重複チェック（先勝ちなので、後段のプロジェクトに同じ語があると到達しない）
    seen: dict[str, str] = {}
    dup = False
    for p in cfg.enrich_projects:
        for kw in p.get("keywords", []):
            if kw in seen and seen[kw] != p["alias"]:
                print(f"⚠️ キーワード重複: '{kw}' が {seen[kw]} と {p['alias']} の両方にある（{seen[kw]} が先勝ち）")
                dup = True
            seen.setdefault(kw, p["alias"])

    rules = classify.load_rules(cfg)
    if rules:
        print(f"\n== classification_rules.jsonl（{len(rules)}件、キーワードより優先） ==")
        for t, proj in rules.items():
            print(f"  '{t}' → {proj}")

    titles = sys.argv[1:]
    if titles:
        print("\n== サンプルタイトル判定 ==")
        for t in titles:
            result = classify.project(t, cfg.enrich_projects, rules)
            norm = classify.normalize_title(t)
            via = "学習ルール" if norm in rules else "キーワード"
            print(f"  '{t}' → {result or '未分類'}（{via}）")

    sys.exit(1 if dup else 0)


if __name__ == "__main__":
    main()
