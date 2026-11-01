# ADR-004 予定の取得元を json / ics のアダプタに分ける

- 状態: 承認
- 日付: 2026-11-01
- 関連: [06 カレンダー照合・メタ情報付加](../specs/06-calendar-enrich.md)、`src/scriba/calendar/`

## 文脈

予定の取得は、外部の定期実行が当日の予定を JSON に書き出し、ファイル同期で手元に届ける一つの経路に固定されていた。読み取り先の既定パスと、同期アプリを起動する処理が、照合や分類と同じモジュールに入っていた。この経路を持たない環境では、予定との照合が使えない。

一方で、多くのカレンダー（Google、Outlook の共有用 URL など）は iCalendar を出せる。

## 決定

- `scriba.calendar` に取得元を閉じ込め、`load_events(cfg, around)` がイベント形式（id, subject, start, end, organizer, showAs。日時は UTC）の一覧を返す
- アダプタは `json`（イベント形式のファイル）と `ics`（ファイルまたは http(s) URL。繰り返しを対象日に展開）の 2 つ
- 照合・分類・frontmatter はイベント形式だけを見る
- イベント形式は旧バージョンが `meta.json` に保存してきた形と同じにする。過去のセッションをそのまま再 enrich できる
- `calendar_source` が空で `calendar_path` だけがあれば `json` とみなす（旧設定との互換）
- 既定の読み取り先と同期アプリの起動はやめる。取得元は設定で明示する

## 却下した案

- **CalDAV、Microsoft Graph、macOS EventKit のアダプタを先に作る**: 認証や権限の扱いが環境ごとに違い、使う人が現れるまで設計が決まらない。ics の URL で多くのカレンダーに届く

## 見直し条件

- ics の URL を出せないカレンダーを使う利用者が現れたとき（そのとき 3 つ目のアダプタを足す）
