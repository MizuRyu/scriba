"""F6: ビューアの HTTP サーバー（`scriba view --serve`）。HTMX パーシャルと編集 API を返す。"""

import json
import re
import subprocess

from scriba.config import Config
from scriba.transcription import transcriber
from scriba.viewer import render

# TOML の bare key。これ以外（ドメインの "." など）は引用符で囲まないと入れ子のキーになる
_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")


def serve(cfg: Config, port: int = 8737) -> None:
    """簡易HTTPサーバーで配信。HTMXパーシャルで自動更新。"""
    import http.server
    from urllib.parse import parse_qs, urlparse

    css = render.css()
    layout = render.layout_template()

    # Content-type map for static assets
    _MIME = {".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8"}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path

            if path in ("/", "/index.html"):
                data = render.collect(cfg)
                html = layout.replace("__CSS__", css).replace(
                    "__GENERATED_AT__", render.esc(data["generated_at"]))
                self._send(200, "text/html; charset=utf-8", html.encode())

            elif path.startswith("/static/"):
                fname = path[len("/static/"):]
                fpath = render.STATIC_DIR / fname
                if fpath.exists() and fpath.is_file():
                    mime = _MIME.get(fpath.suffix, "application/octet-stream")
                    self._send(200, mime, fpath.read_bytes())
                else:
                    self._send(404, "text/plain", b"not found")

            elif path == "/data.json":
                body = json.dumps(render.collect(cfg), ensure_ascii=False).encode()
                self._send(200, "application/json; charset=utf-8", body)

            elif path == "/partial/sessions":
                html = render.sessions_list(cfg)
                self._send(200, "text/html; charset=utf-8", html.encode())

            elif path.startswith("/partial/session/"):
                session_id = path[len("/partial/session/"):]
                html = render.session_detail(cfg, session_id)
                self._send(200, "text/html; charset=utf-8", html.encode())

            elif path == "/partial/performance":
                html = render.performance(cfg)
                self._send(200, "text/html; charset=utf-8", html.encode())

            elif path == "/partial/settings":
                html = render.settings(cfg)
                self._send(200, "text/html; charset=utf-8", html.encode())

            else:
                self._send(404, "text/plain", b"not found")

        def do_POST(self):
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/discard":
                from scriba.recording import recorder

                sid = parse_qs(parsed.query).get("id", [None])[0]
                try:
                    removed = recorder.discard(cfg, sid)
                    self._send(200, "text/plain; charset=utf-8", removed.encode())
                except Exception as e:
                    self._send(400, "text/plain; charset=utf-8", str(e).encode())
            elif path == "/title":
                sid = parse_qs(parsed.query).get("id", [None])[0]
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    title = json.loads(self.rfile.read(length) or b"{}").get("title", "")
                    if not sid:
                        raise ValueError("session id required")
                    meta_file = cfg.session_dir(sid) / "meta.json"
                    if not meta_file.exists():
                        raise FileNotFoundError(f"session not found: {sid}")
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    old_combined = transcriber.find_combined(cfg, sid)
                    meta["title"] = title
                    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
                    if old_combined and old_combined.exists():
                        new_name = transcriber.combined_filename(cfg, sid)
                        new_combined = old_combined.parent / new_name
                        if old_combined != new_combined:
                            old_combined.rename(new_combined)
                    self._send(200, "text/plain; charset=utf-8", title.encode())
                except Exception as e:
                    self._send(400, "text/plain; charset=utf-8", str(e).encode())
            elif path == "/dict":
                from scriba.transcription import dictionary

                try:
                    length = int(self.headers.get("Content-Length", 0))
                    payload = json.loads(self.rfile.read(length) or b"{}")
                    dic = dictionary.from_payload(payload)
                    dictionary.save(cfg.dictionary_path, dic)
                    self._send(200, "application/json; charset=utf-8",
                               json.dumps(render.dict_payload(cfg), ensure_ascii=False).encode())
                except Exception as e:
                    self._send(400, "text/plain; charset=utf-8", str(e).encode())
            elif path == "/enrich":
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    payload = json.loads(self.rfile.read(length) or b"{}")
                    _save_enrich(cfg, payload)
                    self._send(200, "application/json; charset=utf-8",
                               json.dumps(render.enrich_payload(cfg), ensure_ascii=False).encode())
                except Exception as e:
                    self._send(400, "text/plain; charset=utf-8", str(e).encode())
            elif path == "/merge":
                sid = parse_qs(parsed.query).get("id", [None])[0]
                track = parse_qs(parsed.query).get("track", ["both"])[0]
                try:
                    if not sid:
                        raise ValueError("session id required")
                    only_tracks = None if track == "both" else {track}
                    combined = transcriber.merge_session(cfg, sid, only_tracks=only_tracks)
                    # track_filterをmeta.jsonに保存
                    meta_file = cfg.session_dir(sid) / "meta.json"
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    meta["track_filter"] = transcriber.canonical_track(track)
                    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
                    # enrich再適用
                    from scriba import enrich
                    enrich.enrich_session(cfg, sid)
                    self._send(200, "text/plain; charset=utf-8", str(combined).encode())
                except Exception as e:
                    self._send(400, "text/plain; charset=utf-8", str(e).encode())
            elif path == "/export":
                from scriba import export as _export

                sid = parse_qs(parsed.query).get("id", [None])[0]
                override_project = parse_qs(parsed.query).get("project", [None])[0]
                try:
                    if not sid:
                        raise ValueError("session id required")
                    result = _export.export_session(cfg, sid, project_override=override_project or None)
                    if result and not result.get("skipped"):
                        self._send(200, "application/json; charset=utf-8",
                                   json.dumps(result, ensure_ascii=False).encode())
                    elif result and result.get("skipped"):
                        self._send(200, "application/json; charset=utf-8",
                                   json.dumps(result, ensure_ascii=False).encode())
                    else:
                        self._send(400, "text/plain; charset=utf-8", b"export failed")
                except Exception as e:
                    self._send(400, "text/plain; charset=utf-8", str(e).encode())
            else:
                self._send(404, "text/plain", b"not found")

        def _send(self, code: int, ctype: str, body: bytes):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"

    # 消し忘れ対策: 一定時間で自動停止
    import threading
    timeout_min = cfg.serve_timeout_min
    if timeout_min > 0:
        timer = threading.Timer(timeout_min * 60, server.shutdown)
        timer.daemon = True
        timer.start()

    print(f"ビューア起動: {url}（Ctrl+Cで停止、{timeout_min}分で自動停止）")
    subprocess.run(["open", url])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n停止しました")
    else:
        # shutdown() 経由 = タイムアウト
        from scriba.notify import notify
        notify("Scriba", f"ビューアサーバーを{timeout_min}分で自動停止しました")
        print(f"\n{timeout_min}分経過のため自動停止しました")


def _save_enrich(cfg: Config, payload: dict) -> None:
    """config.toml の [enrich] セクションを更新する。"""
    import tomllib

    cfg_file = cfg.base_dir / "config.toml"
    raw: dict = {}
    if cfg_file.exists():
        with open(cfg_file, "rb") as f:
            raw = tomllib.load(f)

    orgs = payload.get("organizations", {})
    projects = payload.get("projects", [])

    raw["enrich"] = {
        "organizations": orgs,
        "projects": projects,
    }

    # config.toml を書き出す（tomllib は読み取り専用なので手動で書く）
    lines: list[str] = []
    enrich_data = raw.pop("enrich")
    for k, v in raw.items():
        if isinstance(v, dict):
            continue  # ネストされたテーブルは後で
        lines.append(_toml_kv(k, v))

    # [enrich] セクション
    lines.append("")
    lines.append("[enrich]")

    # [enrich.organizations]
    if enrich_data.get("organizations"):
        lines.append("")
        lines.append("[enrich.organizations]")
        for domain, name in enrich_data["organizations"].items():
            lines.append(_toml_kv(domain, name))

    # [[enrich.projects]]
    for proj in enrich_data.get("projects", []):
        lines.append("")
        lines.append("[[enrich.projects]]")
        lines.append(_toml_kv("alias", proj.get("alias", "")))
        kws = proj.get("keywords", [])
        lines.append(f"keywords = [{', '.join(_toml_str(k) for k in kws)}]")

    lines.append("")
    cfg_file.write_text("\n".join(lines), encoding="utf-8")

    # ランタイムのcfgも更新
    cfg.enrich_organizations = orgs
    cfg.enrich_projects = projects


def _toml_kv(key: str, value) -> str:
    key = key if _BARE_KEY.fullmatch(key) else _toml_str(key)
    if isinstance(value, bool):
        return f"{key} = {'true' if value else 'false'}"
    if isinstance(value, (int, float)):
        return f"{key} = {value}"
    if isinstance(value, list):
        return f"{key} = [{', '.join(_toml_str(v) for v in value)}]"
    return f"{key} = {_toml_str(value)}"


def _toml_str(s) -> str:
    escaped = str(s).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
