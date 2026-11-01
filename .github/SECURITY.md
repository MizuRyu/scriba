# Security

## データの扱い

scriba は会議の音声を端末内で録音し、端末内で文字起こしします。録音（WAV）、文字起こし、メタ情報、ログはすべて `{base_dir}`（既定 `~/scriba`、`SCRIBA_HOME` で変更可）の下に置きます。テレメトリはありません。

ネットワークに出るのは次の場合だけです。

- 初回の mlx-whisper のモデル取得と、`uvx` / `uv run --with` による依存の取得
- `calendar_source = "ics"` で `calendar_path` に http(s) の URL を設定したときの予定の取得
- `scriba view --serve` のページが読む htmx（unpkg.com）。サーバー自体は `127.0.0.1` だけで待ち受けます

非公開の iCal URL は予定へのアクセス権そのものです。config.toml を共有するときは外してください。

録音は相手の同意を得て行ってください。録音や文字起こしの扱いは、所属組織や会議の取り決めに従ってください。

WAV は `retention_days`（既定 7 日）を過ぎると `scriba start` / `scriba cleanup` で消えます（未文字起こしのものは残します）。セッションごと消すには `scriba discard <id>` を使います。

## 脆弱性の報告

GitHub の Security タブから **Private vulnerability reporting** で報告してください。公開 Issue に実際の会議の音声・文字起こし、予定、認証情報、個人情報を貼らないでください。

報告には、影響するバージョン、macOS の版、合成データでの再現手順、想定した動作と実際の動作を含めてください。

## 検査の範囲

`just security` は Gitleaks で Git 履歴の秘密情報を調べます。依存関係の脆弱性やデータフローを網羅するものではありません。
