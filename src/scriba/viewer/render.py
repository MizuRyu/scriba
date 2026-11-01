"""F6: HTMLビューア。データ埋め込みの静的HTMLを生成する（file://で開ける）。

デザインは docs/DESIGN.md（monoデザインシステム）準拠。
serveモードではHTMXによるパーシャルレンダリングを使用。
"""

import html as _html
import json
from datetime import datetime
from pathlib import Path

from scriba.transcription import transcriber
from scriba.config import Config

# ---------------------------------------------------------------------------
# Asset paths
# ---------------------------------------------------------------------------

_PKG_DIR = Path(__file__).parent
STATIC_DIR = _PKG_DIR / "static"
_TEMPLATES_DIR = _PKG_DIR / "templates"


def _read_asset(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def css() -> str:
    return _read_asset(STATIC_DIR / "style.css")


def layout_template() -> str:
    return _read_asset(_TEMPLATES_DIR / "layout.html")


def _static_template() -> str:
    return _read_asset(_TEMPLATES_DIR / "static.html")


def _app_js() -> str:
    return _read_asset(STATIC_DIR / "app.js")


# ---------------------------------------------------------------------------
# HTML escape helper (server-side)
# ---------------------------------------------------------------------------

def esc(s: object) -> str:
    return _html.escape(str(s)) if s is not None else ""


def _fmt_sec(s: float | None) -> str:
    if s is None:
        return "—"
    m = int(s // 60)
    return f"{m}:{int(s % 60):02d}" if m else f"{s:.1f}s"


# ---------------------------------------------------------------------------
# Serve mode — HTMX partial renderers
# ---------------------------------------------------------------------------

def sessions_list(cfg: Config) -> str:
    """セッション一覧のHTMLパーシャル。5秒ポーリングで自動更新。"""
    data = collect(cfg)
    sessions = data["sessions"]

    if not sessions:
        return (
            '<div hx-get="/partial/sessions" hx-trigger="every 5s" hx-swap="innerHTML" hx-target="#content">'
            '<div class="empty">セッションがありません。scriba start で録音を開始してください。</div>'
            '</div>'
        )

    rows = []
    for s in sessions:
        sid = esc(s["id"])
        row = (
            f'<div class="session-list-item" hx-get="/partial/session/{sid}" '
            f'hx-target="#content" hx-swap="innerHTML" style="cursor:pointer">'
            f'<div class="sl-top">'
            f'<div><span class="sl-date">{esc(s["date"])}</span>'
            f'<span class="sl-time">{esc(s["time_range"])}'
            f'{" · " + esc(s["duration_display"]) if s["duration_display"] != "—" else ""}'
            f'</span>'
            f'{"<span class=sl-time>" + esc(s["title"]) + "</span>" if s.get("title") else ""}'
            f'</div>'
            f'<div class="sl-stats">'
            f'{"<span class=sl-badge>" + esc(s["project"]) + "</span>" if s.get("project") else "<span class=sl-badge-muted>unclassified</span>" if s.get("title") else ""}'
            f'{"<span class=sl-exported>✓ exported</span>" if s.get("exported") else ""}'
            f'{" · " if (s.get("project") or s.get("exported")) and s["chars"] else ""}'
            f'{s["chunks"]} chunks'
            f'{" · " + "{:,}".format(s["chars"]) + " 字" if s["chars"] else ""}'
            f'</div></div>'
            f'<div class="sl-preview">{esc(s["preview"])}</div>'
            f'</div>'
        )
        rows.append(row)

    return (
        '<div hx-get="/partial/sessions" hx-trigger="every 5s" hx-swap="innerHTML" hx-target="#content">'
        + "\n".join(rows)
        + '</div>'
    )


def session_detail(cfg: Config, session_id: str) -> str:
    """セッション詳細のHTMLパーシャル。"""
    data = collect(cfg)
    s = next((x for x in data["sessions"] if x["id"] == session_id), None)
    if s is None:
        return '<div class="empty">セッションが見つかりません。</div>'

    # Transcript blocks
    blocks = s["transcript"].split("\n[")
    transcript_html = ""
    if s["transcript"].strip():
        # Re-add the "[" prefix stripped by split (except first block)
        parts = []
        for i, b in enumerate(blocks):
            b = b.strip()
            if not b:
                continue
            if i > 0:
                b = "[" + b
            lines = b.split("\n")
            parts.append(
                f'<div class="t-chunk">'
                f'<div class="t-time">{esc(lines[0])}</div>'
                f'<p class="t-text">{esc("".join(lines[1:]))}</p>'
                f'</div>'
            )
        transcript_html = "\n".join(parts) if parts else '<div class="empty">文字起こし結果がまだありません。</div>'
    else:
        transcript_html = '<div class="empty">文字起こし結果がまだありません。</div>'

    # Performance sparkline
    perf_html = ""
    if s["per_chunk"]:
        secs = [c["sec"] or 0 for c in s["per_chunk"]]
        mx = max(secs) if secs else 1
        bars = "".join(
            f'<div class="spark" style="height:{round((c["sec"] or 0) / mx * 100) if mx else 0}%" '
            f'data-label="{esc(c["chunk"])}: {(c["sec"] or 0):.1f}s"></div>'
            for c in s["per_chunk"]
        )
        avg = sum(secs) / len(secs)
        perf_html = (
            f'<div class="sparkline-row">{bars}</div>'
            f'<div class="perf-stats">'
            f'<span>Avg: <strong>{avg:.1f}s</strong></span>'
            f'<span>Min: <strong>{min(secs):.1f}s</strong></span>'
            f'<span>Max: <strong>{max(secs):.1f}s</strong></span>'
            f'<span>RTF: <strong>{s["rtf"] if s["rtf"] is not None else "—"}</strong></span>'
            f'</div>'
        )
    else:
        perf_html = '<div class="empty">パフォーマンスログがありません。</div>'

    filename_display = f'sessions/{s["id"]}/transcripts/{s["filename"]}' if s["filename"] else ""

    return f"""\
<div>
  <div style="display:flex; justify-content:space-between; align-items:center;">
    <button class="back" hx-get="/partial/sessions" hx-target="#content" hx-swap="innerHTML"
            onclick="document.getElementById('nav-sessions').classList.add('active')">← Sessions</button>
    <button class="theme-toggle" onclick="discardSession('{esc(session_id)}')">Discard…</button>
  </div>
  <div class="detail-date">{esc(s["date"])}</div>
  <div style="display:flex;align-items:center;gap:0.5rem;margin-top:0.25rem">
    <input id="d-title" value="{esc(s.get('title', ''))}" placeholder="会議名を入力"
           style="flex:1;background:transparent;border:1px solid var(--border);border-radius:0.375rem;padding:0.25rem 0.5rem;font-size:0.9375rem;font-family:inherit;color:var(--fg)">
    <button class="ghost-btn" onclick="saveTitle('{esc(session_id)}')" style="margin-top:0;white-space:nowrap">保存</button>
  </div>
  <div class="detail-time-range">{esc(s["time_range"])}{f" · {s['duration_min']} min" if s["duration_min"] is not None else ""}</div>
  <div class="detail-filename">{esc(filename_display)}</div>
  <div class="meta-row">
    <div><div class="meta-label">Chunks</div><div class="meta-value">{s["chunks"]}</div></div>
    <div><div class="meta-label">Characters</div><div class="meta-value">{s["chars"]:,}</div></div>
    <div><div class="meta-label">Process Time</div><div class="meta-value">{_fmt_sec(s["process_time_sec"])}</div></div>
    <div><div class="meta-label">RTF</div><div class="meta-value">{s["rtf"] if s["rtf"] is not None else "—"}</div></div>
    <div><div class="meta-label">Project</div><div class="meta-value">{_project_badge(s)}</div></div>
    <div><div class="meta-label">Export</div><div class="meta-value">{_export_cell(s, session_id, cfg)}</div></div>
  </div>
  {_track_filter_html(s, session_id)}
  <div class="detail-tabs">
    <button class="detail-tab active" onclick="showDetailView('transcript', this)">Transcript</button>
    <button class="detail-tab" onclick="showDetailView('session-perf', this)">Performance</button>
  </div>
  <div id="detail-transcript" class="detail-view active">{transcript_html}</div>
  <div id="detail-session-perf" class="detail-view">{perf_html}</div>
</div>"""


def performance(cfg: Config) -> str:
    """パフォーマンスダッシュボードのHTMLパーシャル。"""
    data = collect(cfg)
    k = data["kpi"]
    sessions = data["sessions"]
    trend = [t for t in data["trend"] if t["sec"] is not None]

    chars_display = f"{k['chars'] / 1000:.1f}k" if k["chars"] >= 1000 else str(k["chars"])

    # KPI row
    kpi_html = (
        f'<div class="kpi-row">'
        f'<div class="kpi"><div class="kpi-label">Sessions</div><div class="kpi-value">{k["sessions"]}</div><div class="kpi-sub">total</div></div>'
        f'<div class="kpi"><div class="kpi-label">Duration</div><div class="kpi-value">{k["hours"]}h</div><div class="kpi-sub">recorded</div></div>'
        f'<div class="kpi"><div class="kpi-label">Characters</div><div class="kpi-value">{chars_display}</div><div class="kpi-sub">transcribed</div></div>'
        f'<div class="kpi"><div class="kpi-label">Avg RTF</div><div class="kpi-value">{k["avg_rtf"] if k["avg_rtf"] is not None else "—"}</div><div class="kpi-sub">process / audio</div></div>'
        f'</div>'
    )

    # Trend sparkline
    if trend:
        mx = max(1, max(t["sec"] for t in trend))
        bars = "".join(
            f'<div class="spark" style="height:{round(t["sec"] / mx * 100)}%" '
            f'data-label="{esc(t["label"])}: {t["sec"]:.1f}s"></div>'
            for t in trend
        )
        trend_html = f'<div class="sparkline-row">{bars}</div>'
    else:
        trend_html = '<div class="empty">まだデータがありません。</div>'

    trend_stats = (
        f'<div class="perf-stats">'
        f'<span>Model: <strong>{esc(data["model"])}</strong></span>'
        f'<span>Chunk: <strong>{data["chunk_duration"]}s</strong></span>'
        f'<span>Sample Rate: <strong>{data["sample_rate"] / 1000}kHz</strong></span>'
        f'</div>'
    )

    # Session history table
    table_rows = "".join(
        f'<tr><td>{esc(s["date"])}</td><td>{esc(s["time_range"])}</td>'
        f'<td class="num">{str(s["duration_min"]) + " min" if s["duration_min"] is not None else "—"}</td>'
        f'<td class="num">{s["chunks"]}</td>'
        f'<td class="num">{s["rtf"] if s["rtf"] is not None else "—"}</td>'
        f'<td class="num">{"{:,}".format(s["chars"]) if s["chars"] else "—"}</td></tr>'
        for s in sessions
    )
    table_html = (
        '<table class="perf-table">'
        '<tr><th>Date</th><th>Time</th><th class="num">Duration</th>'
        '<th class="num">Chunks</th><th class="num">RTF</th><th class="num">Chars</th></tr>'
        + table_rows
        + '</table>'
    )

    return (
        f'{kpi_html}'
        f'<div class="perf-section">'
        f'<div class="perf-section-title">Processing Time Trend</div>'
        f'{trend_html}{trend_stats}'
        f'</div>'
        f'<div class="perf-section">'
        f'<div class="perf-section-title">Session History</div>'
        f'{table_html}'
        f'</div>'
    )


def settings(cfg: Config) -> str:
    """Settings (Dictionary + Enrich) のHTMLパーシャル。"""
    d = dict_payload(cfg)
    e = enrich_payload(cfg)

    # --- Dictionary section ---
    terms_rows = ""
    terms = d["terms"] if d["terms"] else [{"word": ""}]
    for t in terms:
        terms_rows += (
            f'<div class="dict-row">'
            f'<input class="term-word" value="{esc(t["word"])}" placeholder="用語（例: 山田）" oninput="onDictInput()">'
            f'<button class="row-del" onclick="this.closest(\'.dict-row\').remove(); onDictInput()">×</button>'
            f'</div>'
        )

    repl_rows = ""
    repls = d["replacements"] if d["replacements"] else [{"from": "", "to": ""}]
    for r in repls:
        repl_rows += (
            f'<div class="dict-row">'
            f'<input class="repl-from" value="{esc(r["from"])}" placeholder="誤（例: バックローリー）" oninput="onDictInput()">'
            f'<span class="dict-arrow">→</span>'
            f'<input class="repl-to" value="{esc(r["to"])}" placeholder="正（例: バックログ）" oninput="onDictInput()">'
            f'<button class="row-del" onclick="this.closest(\'.dict-row\').remove(); onDictInput()">×</button>'
            f'</div>'
        )

    defaults_html = ""
    if d["default_filters"]:
        defaults_html = "".join(
            f'<span class="dict-default-item">{esc(f)}</span>' for f in d["default_filters"]
        )
    else:
        defaults_html = '<span class="dict-default-item">なし</span>'

    filter_rows = ""
    filters = d["filters"] if d["filters"] else [{"value": ""}]
    for f in filters:
        filter_rows += (
            f'<div class="dict-row">'
            f'<input class="filter-value" value="{esc(f["value"])}" placeholder="除去する発話（例: ありがとうございました）">'
            f'<button class="row-del" onclick="this.closest(\'.dict-row\').remove()">×</button>'
            f'</div>'
        )

    prompt_status_class = "ok"
    prompt_status_text = ""
    n = len(d["prompt"])
    if n > 150:
        prompt_status_class = "block"
        prompt_status_text = f"{n}文字（上限超の恐れ、減らしてください）"
    elif n > 120:
        prompt_status_class = "warn"
        prompt_status_text = f"{n}文字（上限に接近）"
    elif n > 0:
        prompt_status_class = "ok"
        prompt_status_text = f"{n}文字"

    hint = "Whisperに事前に渡す頻出語。人名・プロジェクト名・専門用語など。上限あり（224トークン）。"
    engine_attr = ""
    if cfg.model.startswith("haas-"):
        hint = "Haasに渡す頻出語。読みを添えるときは「Haas=ハース」の形で入力します。"
        prompt_status_class = d["verdict"]
        prompt_status_text = d["message"]
        engine_attr = ' data-engine="haas"'

    dict_section = f"""\
    <div id="dict-editor"{engine_attr}>
      <div class="perf-section">
        <div class="perf-section-title">認識ヒント（用語）</div>
        <div class="dict-hint">{hint}<span id="dict-prompt-status" class="dict-status {prompt_status_class}">{prompt_status_text}</span></div>
        <div id="terms-list">{terms_rows}</div>
        <button class="ghost-btn" onclick="addRow('terms-list', 'term')">+ 用語を追加</button>
        <div class="dict-prompt-preview" id="dict-prompt-preview">{esc(d["prompt"])}</div>
      </div>
      <div class="perf-section">
        <div class="perf-section-title">置換ルール</div>
        <div class="dict-hint">文字起こし後に「誤 → 正」で一括置換。件数制限なし。誤変換された固有名詞の修正に。</div>
        <div id="repl-list">{repl_rows}</div>
        <button class="ghost-btn" onclick="addRow('repl-list', 'repl')">+ 置換を追加</button>
      </div>
      <div class="perf-section">
        <div class="perf-section-title">フィルタ（この発話だけのセグメントを除去）</div>
        <div class="dict-hint">セグメントがこの文字列だけ（前後空白・末尾の句読点を除く）のとき combined から除去。幻聴定型や単独の相槌向け。デフォルトとユーザー登録分の和集合で除去されます。</div>
        <div class="dict-default-label">内蔵デフォルト（編集不可）</div>
        <div id="filter-default-list" class="dict-default-list">{defaults_html}</div>
        <div class="dict-default-label">ユーザー登録</div>
        <div id="filter-list">{filter_rows}</div>
        <button class="ghost-btn" onclick="addRow('filter-list', 'filter')">+ フィルタを追加</button>
      </div>
      <div class="dict-actions">
        <button class="primary-btn" onclick="saveDict()">保存</button>
        <span class="dict-status" id="dict-save-status"></span>
        <span class="detail-filename" id="dict-path" style="margin-left:auto">{esc(d["path"])}</span>
      </div>
    </div>"""

    # --- Enrich section ---
    orgs = e.get("organizations") or {}
    org_entries = list(orgs.items()) if orgs else [("", "")]
    org_rows = ""
    for domain, name in org_entries:
        org_rows += (
            f'<div class="dict-row">'
            f'<input class="enrich-org-domain" value="{esc(domain)}" placeholder="ドメイン（例: example.com）">'
            f'<span class="dict-arrow">→</span>'
            f'<input class="enrich-org-name" value="{esc(name)}" placeholder="組織名（例: Example 社）">'
            f'<button class="row-del" onclick="this.closest(\'.dict-row\').remove()">×</button>'
            f'</div>'
        )

    projects = e.get("projects") or []
    proj_list = projects if projects else [{"alias": "", "keywords": []}]
    proj_rows = ""
    for p in proj_list:
        kw = ", ".join(p.get("keywords", [])) if isinstance(p.get("keywords"), list) else (p.get("keywords") or "")
        proj_rows += (
            f'<div class="dict-row">'
            f'<input class="enrich-proj-alias" value="{esc(p.get("alias", ""))}" placeholder="エイリアス（例: acme）" style="flex:0.6">'
            f'<input class="enrich-proj-keywords" value="{esc(kw)}" placeholder="キーワード（カンマ区切り）" style="flex:1">'
            f'<button class="order-btn" onclick="moveEnrichRow(this, -1)">↑</button>'
            f'<button class="order-btn" onclick="moveEnrichRow(this, 1)">↓</button>'
            f'<button class="row-del" onclick="this.closest(\'.dict-row\').remove()">×</button>'
            f'</div>'
        )

    enrich_section = f"""\
    <div id="enrich-editor">
      <div class="perf-section">
        <div class="perf-section-title">カレンダーパス</div>
        <div class="dict-hint">予定の取得元（json のファイル、ics のファイルまたは URL）。config.toml の calendar_source と calendar_path で変更する。</div>
        <div class="dict-row">
          <input id="enrich-calendar-path" value="{esc(e.get('calendar_path', ''))}" readonly style="flex:1;background:var(--light);color:var(--muted);cursor:default">
        </div>
      </div>
      <div class="perf-section">
        <div class="perf-section-title">組織マッピング</div>
        <div class="dict-hint">メールアドレスのドメインから組織名を推定するマッピング。</div>
        <div id="enrich-orgs-list">{org_rows}</div>
        <button class="ghost-btn" onclick="addEnrichOrg()">+ 組織を追加</button>
      </div>
      <div class="perf-section">
        <div class="perf-section-title">プロジェクトマッピング</div>
        <div class="dict-hint">会議タイトルのキーワードからプロジェクトを推定するルール。上から順に評価されます。</div>
        <div id="enrich-projects-list">{proj_rows}</div>
        <button class="ghost-btn" onclick="addEnrichProject()">+ プロジェクトを追加</button>
      </div>
      <div class="dict-actions">
        <button class="primary-btn" onclick="saveEnrich()">保存</button>
        <span class="dict-status" id="enrich-save-status"></span>
      </div>
    </div>"""

    # Sub-nav tabs use JS to toggle visibility (no extra server call needed)
    # All JS functions are loaded from /static/serve.js via layout.html
    return f"""\
<div class="sub-nav">
  <button class="sub-nav-link active" onclick="showSubTab('dict')">Dictionary</button>
  <button class="sub-nav-link" onclick="showSubTab('enrich')">Enrich</button>
</div>
<div id="sub-dict" class="sub-view active">
{dict_section}
</div>
<div id="sub-enrich" class="sub-view">
{enrich_section}
</div>"""


# ---------------------------------------------------------------------------
# Static HTML generation (unchanged architecture — data embedded in template)
# ---------------------------------------------------------------------------

def generate(cfg: Config) -> Path:
    data = collect(cfg)
    out_dir = cfg.base_dir / "view"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "index.html"

    style = css()
    template = _static_template()
    js = _app_js()

    html = template.replace("__CSS__", style).replace(
        "__APP_JS__", js.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    )
    out.write_text(html, encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Data collection helpers
# ---------------------------------------------------------------------------

def collect(cfg: Config) -> dict:
    perf_by_session: dict[str, list[dict]] = {}
    if cfg.perf_log.exists():
        for line in cfg.perf_log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            perf_by_session.setdefault(e["session"], []).append(e)

    sessions = []
    if cfg.sessions_dir.exists():
        for sdir in sorted(cfg.sessions_dir.iterdir(), reverse=True):
            if not sdir.is_dir():
                continue
            meta = {}
            meta_file = sdir / "meta.json"
            if meta_file.exists():
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            combined = transcriber.find_combined(cfg, sdir.name)
            transcript = combined.read_text(encoding="utf-8") if combined else ""
            if transcript.startswith("---\n"):
                end_fm = transcript.find("\n---\n", 4)
                if end_fm != -1:
                    transcript = transcript[end_fm + 5:]
            perf = perf_by_session.get(sdir.name, [])
            audio_total = sum(e.get("audio_duration_sec") or 0 for e in perf)
            proc_total = sum(e.get("process_time_sec") or 0 for e in perf)

            started = _parse_dt(meta.get("started_at"), sdir.name, cfg.session_format)
            stopped = _parse_dt(meta.get("stopped_at"), None, None)
            time_range = started.strftime("%H:%M") if started else "—"
            if started and stopped:
                time_range += f" - {stopped.strftime('%H:%M')}"
            dur_min = int((stopped - started).total_seconds() / 60) if started and stopped else None

            combined_name = combined.name if combined else ""

            text_only = "".join(
                ln for ln in transcript.splitlines() if ln and not ln.startswith("[")
            )
            sessions.append({
                "id": sdir.name,
                "filename": combined_name,
                "title": meta.get("title", ""),
                "date": started.strftime("%Y/%m/%d") if started else sdir.name,
                "time_range": time_range,
                "duration_min": dur_min,
                "duration_display": f"{dur_min // 60}h{dur_min % 60:02d}m" if dur_min is not None else "—",
                "chunks": transcriber.count_system(sdir / "chunks", ".wav") or len(
                    {e["chunk"] for e in perf}
                ),
                "chars": len(text_only),
                "process_time_sec": round(proc_total, 1),
                "rtf": round(proc_total / audio_total, 3) if audio_total else None,
                "preview": text_only[:60],
                "transcript": transcript,
                "per_chunk": [
                    {"chunk": e["chunk"], "sec": e.get("process_time_sec")}
                    for e in perf
                ],
                "project": _resolve_project(meta, cfg),
                "exported": bool(meta.get("exported_at")),
                "has_mic": "mic" in meta.get("tracks", []),
                "track_filter": meta.get("track_filter", "both"),
            })

    all_perf = [e for es in perf_by_session.values() for e in es]
    audio_all = sum(e.get("audio_duration_sec") or 0 for e in all_perf)
    proc_all = sum(e.get("process_time_sec") or 0 for e in all_perf)
    return {
        "generated_at": datetime.now().strftime("%Y/%m/%d %H:%M"),
        "model": cfg.model.rsplit("/", 1)[-1],
        "chunk_duration": cfg.chunk_duration,
        "sample_rate": cfg.sample_rate,
        "sessions": sessions,
        "kpi": {
            "sessions": len(sessions),
            "hours": round(audio_all / 3600, 1),
            "chars": sum(s["chars"] for s in sessions),
            "avg_rtf": round(proc_all / audio_all, 3) if audio_all else None,
        },
        "trend": [
            {"label": f"{e['session']}/{e['chunk']}", "sec": e.get("process_time_sec")}
            for e in all_perf[-60:]
        ],
        "dict": dict_payload(cfg),
        "enrich": enrich_payload(cfg),
    }


def _track_filter_html(s: dict, session_id: str) -> str:
    if not s.get("has_mic"):
        return ""
    q = "'"
    current = transcriber.canonical_track(s.get("track_filter", "both"))
    def btn(label, value):
        active = " active" if current == value else ""
        return f'<button class="detail-tab{active}" onclick="remerge({q}{esc(session_id)}{q},{q}{value}{q})">{label}</button>'
    return (
        f'<div style="margin:0.75rem 0 0.25rem;font-size:0.8125rem;color:var(--muted)">トラック</div>'
        f'<div class="detail-tabs">'
        f'{btn("両方", "both")}{btn("相手のみ", "system")}{btn("自分のみ", "mic")}'
        f'</div>'
    )


def _project_badge(s: dict) -> str:
    if s.get("project"):
        return f'<span class="sl-badge">{esc(s["project"])}</span>'
    return '<span class="sl-badge-muted">unclassified</span>'


def _export_cell(s: dict, session_id: str, cfg: Config) -> str:
    if s.get("exported"):
        return '<span class="sl-exported">✓ exported</span>'
    q = "'"
    # 常にドロップダウン: 確定済みprojectはプリセレクト。notes行きも選べる
    current = s.get("project") or ""
    options = "".join(
        f'<option value="{esc(p["alias"])}"{" selected" if p["alias"] == current else ""}>{esc(p["alias"])}</option>'
        for p in cfg.enrich_projects
    )
    return (
        f'<select id="export-proj-{esc(session_id)}" style="font-size:0.8125rem;padding:0.125rem 0.25rem;border:1px solid var(--border);border-radius:0.25rem;background:var(--card);color:var(--fg)">'
        f'<option value=""{" selected" if not current else ""}>未分類</option>'
        f'{options}'
        f'</select> '
        f'<button class="ghost-btn" onclick="exportWithProject({q}{esc(session_id)}{q})">転送</button>'
    )


def _resolve_project(meta: dict, cfg: Config) -> str | None:
    if meta.get("project"):
        return meta["project"]
    enrich_data = meta.get("enrich")
    if not enrich_data:
        return None
    from scriba import enrich
    fm = enrich.build_enrich_meta(enrich_data, cfg)
    return fm.get("project")


def dict_payload(cfg: Config) -> dict:
    from scriba.transcription import dictionary

    dic = dictionary.load(cfg.dictionary_path)
    prompt = dic.build_prompt(cfg.model)
    verdict, message = dictionary.validate_prompt(prompt, cfg.model)
    return {
        "terms": [{"word": t["word"]} for t in dic.terms],
        "replacements": [{"from": k, "to": v} for k, v in dic.replacements.items()],
        "filters": [{"value": f} for f in dic.filters],
        "default_filters": list(dictionary.DEFAULT_FILTERS),
        "prompt": prompt,
        "verdict": verdict,
        "message": message,
        "path": str(cfg.dictionary_path),
    }


def enrich_payload(cfg: Config) -> dict:
    return {
        "calendar_path": cfg.calendar_path,
        "organizations": cfg.enrich_organizations or {},
        "projects": cfg.enrich_projects or [],
    }


def _parse_dt(iso: str | None, session_id: str | None, fmt: str | None):
    if iso:
        try:
            return datetime.fromisoformat(iso)
        except ValueError:
            pass
    if session_id and fmt:
        try:
            return datetime.strptime(session_id, fmt)
        except ValueError:
            pass
    return None
