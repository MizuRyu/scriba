---
name: add-project
description: scriba に案件を登録し、会議の transcript が自動で分類・転送されるようにする。新しい案件や顧客の仕事が始まったとき、「新しいプロジェクト追加して」「◯◯案件を scriba に登録」「案件が増えたから設定して」などで使う。config.toml の [[enrich.projects]] と [enrich.organizations] を更新し、キーワードの順序を決め、学習済みの仕訳ルールとの衝突を確かめる。
---

# add-project — scriba に案件を登録する

新しい案件が始まったとき、会議の transcript が自動で分類されるように、scriba の enrich 設定を更新する。仕様は `docs/specs/06-calendar-enrich.md`。

## 前提

- 設定と学習データの置き場は `${SCRIBA_HOME:-~/scriba}`（以下 `{base_dir}`）
- 案件の判定は 2 段階: **① `{base_dir}/classification_rules.jsonl`（export 時に学習したルール。優先）② `config.toml` のキーワード**（定義順に評価し、最初に当たったもの）
- alias は転送先のフォルダ名になる（`{export_dir}/{export_subdir}` の `{project}`）。利用者が別の場所で案件の一覧を管理しているなら、その alias に合わせる。分からなければ利用者に聞き、勝手に作らない
- 転送先のフォルダは初回の export で作られる。事前の準備は要らない

## 手順

### 1. alias を決める

追加する案件の alias を利用者と確定する。既存の `[[enrich.projects]]` の alias と重ならないこと。

### 2. キーワードを集める

実際の会議名からキーワードを決める。材料の優先順:

1. 利用者に実際の会議名の例を聞く
2. 予定の取得元（`calendar_path` の JSON や ics）に、その案件の予定があれば subject を見る

キーワードの注意:

- 「定例」「MTG」「打ち合わせ」のような汎用語は使わない（他の案件に誤って当たる）
- 顧客名、案件名、システム名など、その案件に固有の語を選ぶ
- 表記ゆれ（例:「請求」「ご請求」）は両方入れる

### 3. config.toml を編集する

`{base_dir}/config.toml` の `[[enrich.projects]]` にブロックを足す:

```toml
[[enrich.projects]]
alias = "<alias>"
keywords = ["固有キーワード1", "固有キーワード2"]
```

**順序のルール（最重要）**: 評価は上から先勝ち。より限定的なキーワードを持つ案件を上に置く。例: 同じ顧客 ACME に「ACME 請求」の案件 `acme-billing` と、ACME 全般の案件 `acme` があるなら、`acme-billing` を `acme` より前に置く。逆にすると「ACME 請求」の会議が `acme` に吸われる。社内会議用の案件（`internal` など）は最後に置く。

新しい案件のキーワードが既存の案件の会議名にも現れうるときは、挿入位置を慎重に決める。

### 4. 組織のドメインを足す（該当するときだけ）

新しい顧客のメールドメインが増えるなら `[enrich.organizations]` に足す:

```toml
[enrich.organizations]
"newclient.example" = "New Client"
```

### 5. 検証する

リポジトリのルートで検証スクリプトを実行する。実際の会議名の例を引数に渡す:

```bash
uv run python .agents/skills/add-project/scripts/verify.py "実際の会議名1" "会議名2"
```

出力で確かめること:

- 定義一覧の順序が意図どおりか
- キーワードの重複警告（⚠️）が出ていないか
- 会議名の例が正しい alias に判定されるか

### 6. 学習済みルールとの衝突を確かめる

verify.py は `classification_rules.jsonl` の内容も表示する。**学習ルールはキーワードより優先される**ので、新しい案件に当たるべき会議名が過去に別の案件で学習されていたら、利用者に確認したうえで `{base_dir}/classification_rules.jsonl` の該当行を消す。

## UI での代わりの手段

`scriba view --serve` → Settings → Enrich でも編集できる。ただし順序の制御と検証は、この手順（直接編集と verify.py）の方が確実。
