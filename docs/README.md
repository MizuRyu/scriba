# ドキュメント

どのファイルが有効な仕様かを、ここで一元管理する。

## 使う

| ファイル | 内容 |
|---|---|
| [../README.md](../README.md) | 概要、インストール、基本操作 |
| [background.md](background.md) | これは何か、なぜ作ったか、コードに書かれていない前提、設計の芯、普段の使われ方、制約、旧バージョンからの変更 |
| [usage.md](usage.md) | セットアップ、コマンド、自動録音、予定との照合、転送、設定、辞書、データの場所、トラブルシュート |
| [../.github/SECURITY.md](../.github/SECURITY.md) | データの扱いと脆弱性の報告 |
| [third-party-licenses.md](third-party-licenses.md) | 実行時に使うソフトウェアのライセンス |

## 開発する

| ファイル | 内容 |
|---|---|
| [development.md](development.md) | 環境、コマンド、テスト（golden）、コミット前の検査 |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | 変更の進め方と守ること |
| [DESIGN.md](DESIGN.md) | ビューアのデザインシステム（mono） |

案件の登録手順は `.agents/skills/add-project/SKILL.md`。

## 仕様と判断

| ファイル | 内容 |
|---|---|
| [specs/README.md](specs/README.md) | 仕様の索引と、どこを更新するか |
| [adr/README.md](adr/README.md) | 技術判断の理由と見直し条件 |
| [research/](research/) | 調査の記録（判断の材料。現行仕様ではない） |

- 挙動を変えたら [specs/](specs/README.md) の該当ファイル、利用者に見える変更なら [usage.md](usage.md)、開発コマンドを変えたら [development.md](development.md)。
- 「なぜそうしたか」が変わったら [adr/](adr/README.md) に追加する。既存の ADR は書き換えない。
- README は入口だけを持つ。詳細はここから参照し、説明を重複させない。
