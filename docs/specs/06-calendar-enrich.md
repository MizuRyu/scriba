# 06 カレンダー照合・メタ情報付加

## 目的

1. 録音したセッションに、予定表の会議名を自動で付ける
2. 会議の組織と案件を推定し、文字起こしファイルの frontmatter に付ける
3. 後続の処理（案件フォルダへの振り分け、LLM による要約など）が本文を読まずに会議を特定できる状態にする

判断はすべて決定論的なルールで行い、LLM は呼ばない。

## 予定の取得元（アダプタ）

`scriba.calendar` が取得元の違いを吸収し、どのアダプタも同じ**イベント形式**を返す。照合・分類・frontmatter はイベント形式だけを見る。

| `calendar_source` | `calendar_path` | 読む範囲 | 想定する運用 |
|---|---|---|---|
| `json` | JSON ファイル | ファイルの全予定 | 外部の定期実行（Power Automate など）が当日の予定を書き出し、ファイル同期で届ける |
| `ics` | .ics ファイル、または http(s) の URL | 対象日の予定（繰り返し予定は展開） | Google カレンダーや Outlook の公開・共有用 iCal URL |
| 空 | 空 | 照合しない | — |

`calendar_source` が空で `calendar_path` だけがあるときは `json` として扱う（旧バージョンの設定との互換）。

### イベント形式

```json
{"events": [
  {"id": "evt-1", "subject": "【ACME】定例", "start": "2026-07-06T00:15:00", "end": "2026-07-06T01:00:00",
   "organizer": "alice@acme.example", "showAs": "busy"}
]}
```

| フィールド | 内容 |
|---|---|
| `id` | 予定の識別子 |
| `subject` | 会議名。セッションの `title` と分類の材料 |
| `start` / `end` | UTC の ISO 8601（タイムゾーン表記なし。小数秒は任意） |
| `organizer` | 主催者のメールアドレス。組織推定の材料 |
| `showAs` | `busy` / `tentative` / `free` など（参考情報） |

`json` アダプタはこの形式のファイルをそのまま読む。キャンセル済みと終日の予定は、書き出す側で除いておく。

`ics` アダプタは VEVENT を次のように変換する。

- `SUMMARY` → `subject`、`UID` → `id`、`ORGANIZER`（`mailto:` を除く）→ `organizer`
- `DTSTART` / `DTEND`（なければ `DURATION`）→ UTC に変換。タイムゾーン指定のない時刻はローカル時刻とみなす
- `STATUS:TENTATIVE` → `tentative`、`TRANSP:TRANSPARENT` → `free`、それ以外 → `busy`
- `STATUS:CANCELLED` と終日予定（日付だけの `DTSTART`）は除く

### エラー時

予定が取れなくても録音と文字起こしは止めない。title が空のまま続行する。

- ファイルがない・JSON が壊れている → 空として扱う
- `json` の先頭の予定が今日の日付でない → 書き出し側が止まっている可能性を警告
- ics が読めない（ファイルなし、通信失敗、解析失敗）→ 警告して空として扱う
- 未対応の `calendar_source` → 警告して空として扱う

## 照合

`scriba start` の時刻（`scriba enrich` ではセッションの `started_at`）を `T` とし、開始時刻が `T` から 10 分以内の予定を候補にする。

| 候補 | 動作 |
|---|---|
| 1 件、または開始時刻が最も近いものが 1 件 | その予定を採用。`meta.json` の `enrich` に予定を、`title` に `subject` を書く |
| 開始時刻が同じ予定が複数 | 自動では決めない。候補を表示し、`scriba title` での設定を促す |
| なし | title は空のまま。後から `scriba title` で付ける |

時刻の表示と frontmatter の日時は、OS のローカルタイムゾーンで出す。

## メタ情報の推定（`scriba.classify`）

### 組織

organizer のメールドメインを `[enrich.organizations]` で引く。完全一致がなければ親ドメインを順にたどる（`sales.acme.example` → `acme.example`）。どれにも当たらなければドメイン名をそのまま使う。

```toml
[enrich.organizations]
"acme.example" = "ACME"
```

組織は参考情報で、案件の判定には使わない（同じ組織に複数の案件がありうるため）。

### 案件

評価順:

1. **仕訳ルール**（`{base_dir}/classification_rules.jsonl`）: 正規化した会議名が一致すれば、その案件
2. **キーワード**（`[[enrich.projects]]`）: 定義順に評価し、`subject` にキーワードを含む最初の案件
3. どれにも当たらなければ `null`（未分類）

```toml
[[enrich.projects]]
alias = "acme-billing"
keywords = ["請求", "ACME Billing"]

[[enrich.projects]]
alias = "acme"
keywords = ["ACME"]

# 社内会議は最後に置く（客先名を含む社内の振り返りは客先の案件を優先する）
[[enrich.projects]]
alias = "internal"
keywords = ["（内部）", "社内"]
```

**順序が重要**: より限定的なキーワードを持つ案件を上に置く。上の例で `acme` を先に置くと、「ACME 請求」の会議が `acme` に吸われる。

### 仕訳ルールの学習

export したとき、会議名を正規化して案件と対にし、`classification_rules.jsonl` に追記する。次回から同じ定例はキーワードより先に、この対で分類される。

```jsonl
{"title_normalized": "ACME 定例", "title_original": "ACME 定例 7/6", "project": "acme", "created_at": "2026-07-06T10:05:00"}
```

正規化で取り除くもの: 日付（`2026-07-06`、`7/6`）、回数（`第3回`）、末尾の年（`_2026`）。

## frontmatter

`scriba stop` と `scriba enrich` が combined の先頭に付ける。`scriba merge` で本文を作り直しても引き継ぐ。

```yaml
---
title: "【ACME】定例"
date: 2026-07-06
start: "09:15"
end: "10:00"
organization: ACME
project: acme
source_session: 20260706-091500
---
```

## 処理のタイミング

1. **`scriba start`**: 予定を取得して照合し、結果を `meta.json` に書く
2. **`scriba stop`**: `meta.json` の照合結果から frontmatter を作って付ける。title と照合結果がそろっていれば export する（タイムアウト停止のときはどちらもしない）
3. **`scriba enrich <session|latest>`**: 照合からやり直す（マッピングを直した後の再適用）

## 設定

| キー | 既定 | 内容 |
|---|---|---|
| `calendar_source` | 空 | `json` \| `ics` |
| `calendar_path` | 空 | json: ファイル / ics: ファイルまたは http(s) URL |
| `[enrich.organizations]` | なし | ドメイン → 組織名 |
| `[[enrich.projects]]` | なし | `alias` と `keywords`。定義順に評価 |

組織と案件のマッピングは `scriba view --serve` の Settings > Enrich でも編集できる。案件の追加手順と検証は `.agents/skills/add-project/SKILL.md`。
