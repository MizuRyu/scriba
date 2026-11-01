# 仕様

| ファイル | 内容 |
|---|---|
| [01-overview.md](01-overview.md) | 目的、前提環境、スコープ |
| [02-architecture.md](02-architecture.md) | コンポーネント、状態管理、データの置き場 |
| [03-features.md](03-features.md) | 機能（F1〜F12）と設定項目 |
| [04-workflow.md](04-workflow.md) | live / record-only の流れ、エラーケース |
| [05-model-selection.md](05-model-selection.md) | 文字起こしモデルの比較と採用理由 |
| [06-calendar-enrich.md](06-calendar-enrich.md) | 予定の取得元（json / ics）、照合、組織・案件の推定、frontmatter |
| [07-project-structure.md](07-project-structure.md) | ディレクトリ構成と責務の線 |

## どこを更新するか

- 挙動を変えたら、該当する機能の節（03 の F 番号、06）を更新する
- 設定項目を足したら、03 の該当機能の「設定項目」と [usage.md](../usage.md) の設定表の両方
- ファイルを足したり動かしたりしたら 07
- 判断の理由が変わったら [adr/](../adr/README.md) に追加する
