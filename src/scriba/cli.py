"""scriba CLI: start / stop / status / transcribe / merge / title / enrich / view / dict / cleanup / worker"""

import argparse
import json
import subprocess
import sys
from datetime import datetime

from scriba import calendar, config, enrich, export
from scriba.recording import audio, recorder
from scriba.transcription import dictionary, haas, transcriber
from scriba.viewer import render, server


def main() -> None:
    parser = argparse.ArgumentParser(prog="scriba", description="オンライン会議のローカル録音・逐次文字起こし")
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="録音開始")
    p_start.add_argument("--mode", choices=["live", "record-only"], default=None)

    p_stop = sub.add_parser("stop", help="録音停止")
    # 内部用（自動停止）: 録音中がこのセッションのときだけ止める
    p_stop.add_argument("--only-session", help=argparse.SUPPRESS)

    p_status = sub.add_parser("status", help="状態表示")
    p_status.add_argument("--quiet", action="store_true", help="録音中なら終了コード0、それ以外は1")

    p_tr = sub.add_parser("transcribe", help="未処理チャンクの一括文字起こし")
    p_tr.add_argument("session", nargs="?", help="セッションID（省略時は--allが必要）")
    p_tr.add_argument("--all", action="store_true", help="全未処理セッションを処理")

    sub.add_parser("setup-model", help="Haas の実行ファイルとモデルを事前に取得・検証")

    p_merge = sub.add_parser("merge", help="combined を再生成（辞書・フィルタ・--until を再適用）")
    p_merge.add_argument("session", help="セッションID")
    p_merge.add_argument("--until", type=float, default=None, help="この分数以降に開始するセグメントを除外")
    # teams は system の旧名
    p_merge.add_argument("--track", choices=["system", "teams", "mic", "both"], default="both", help="使用するトラック（system=相手のみ, mic=自分のみ, both=両方）")

    p_title = sub.add_parser("title", help="会議名を後付け（session に latest 指定可）")
    p_title.add_argument("session", help="セッションID または latest")
    p_title.add_argument("title", help="会議名")

    p_export = sub.add_parser("export", help="transcriptを export_dir に転送")
    p_export.add_argument("session", nargs="?", help="セッションID（省略で全未転送）")
    p_export.add_argument("--project", help="案件名を指定して転送（session 省略時は未分類のものだけに適用）")

    p_enrich = sub.add_parser("enrich", help="カレンダー照合・メタ情報付加を再実行")
    p_enrich.add_argument("session", help="セッションID または latest")

    p_view = sub.add_parser("view", help="HTMLビューアを生成して開く")
    p_view.add_argument("--serve", action="store_true", help="HTTPサーバーモード（5秒自動更新 + ワンクリックDiscard）")
    p_view.add_argument("--port", type=int, default=8737)

    p_discard = sub.add_parser("discard", help="セッションを破棄（録音中なら中止して破棄、IDなしなら最新）")
    p_discard.add_argument("session", nargs="?", help="セッションID")
    p_discard.add_argument("--yes", "-y", action="store_true", help="確認をスキップ")

    p_dict = sub.add_parser("dict", help="辞書の操作")
    p_dict.add_argument("action", choices=["validate", "show"])

    sub.add_parser("cleanup", help="保持期間を超えた録音ファイルを削除")

    p_watch = sub.add_parser("watch", help="自動録音（会議の開始・終了で録音を開始・停止）")
    p_watch.add_argument("action", choices=["on", "off", "toggle", "run"], help="run は内部用（常駐プロセス本体）")

    p_worker = sub.add_parser("worker")  # 内部用（liveモードのバックグラウンドワーカー）
    p_worker.add_argument("session")

    p_record = sub.add_parser("record")  # 内部用（sounddevice録音プロセス）
    p_record.add_argument("session")
    p_record.add_argument("--mic", action="store_true")

    args = parser.parse_args()
    cfg = config.load()
    cfg.base_dir.mkdir(parents=True, exist_ok=True)

    try:
        _dispatch(args, cfg)
    except (recorder.RecorderError, audio.AudioGuardError, haas.HaasError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)


def _resolve_session(cfg, session: str) -> str:
    """latest なら最新セッション（録音中ならそれ）を返す。それ以外はそのまま。"""
    if session != "latest":
        return session
    st = recorder.status(cfg)
    if st:
        return st["session_id"]
    sessions = (
        sorted(p.name for p in cfg.sessions_dir.iterdir() if p.is_dir())
        if cfg.sessions_dir.exists() else []
    )
    if not sessions:
        print("セッションがありません", file=sys.stderr)
        sys.exit(1)
    return sessions[-1]


def _export(cfg, session: str | None, project: str | None) -> None:
    if session:
        results = [export.export_session(cfg, _resolve_session(cfg, session), project_override=project)]
    else:
        sessions = sorted(p.name for p in cfg.sessions_dir.iterdir() if p.is_dir()) if cfg.sessions_dir.exists() else []
        results = [_export_unclassified_as(cfg, sid, project) for sid in sessions]
    exported = [r for r in results if r and not r.get("skipped")]
    for r in exported:
        print(f"転送: {r['path']} (project: {r.get('project')})")
    print(f"完了: {len(exported)}件転送")


def _export_unclassified_as(cfg, sid: str, project: str | None) -> dict | None:
    """分類済みは自分の project で、未分類だけ指定の project で転送する。"""
    result = export.export_session(cfg, sid)
    if project and result and result.get("reason") == "unclassified":
        return export.export_session(cfg, sid, project_override=project)
    return result


def _watch(cfg, action: str) -> None:
    from scriba.meeting import watch

    if action == "run":
        watch.run(cfg)
        return
    if action == "toggle":
        action = "off" if watch.running_pid(cfg) else "on"
    if action == "on":
        print("自動録音: 有効にしました" if watch.enable(cfg) else "自動録音: 既に有効です")
    else:
        print("自動録音: 無効にしました" if watch.disable(cfg) else "自動録音: 既に無効です")


def _dispatch(args, cfg) -> None:
    if args.command == "setup-model":
        if not cfg.model.startswith("haas-"):
            raise haas.HaasError("setup-model は Haas 用です。model に haas-ja-v1.0:q4_k を指定してください")
        haas.setup(cfg.base_dir, cfg.model)
        print(f"モデルを準備しました: {cfg.model}")

    elif args.command == "start":
        removed = recorder.cleanup(cfg)
        for r in removed:
            print(f"クリーンアップ: {r}")
        mode = args.mode or cfg.mode
        session_id = recorder.start(cfg, mode)
        print(f"録音開始（{mode}）: {session_id}")
        print("停止: scriba stop")

    elif args.command == "stop":
        session_id = recorder.stop(cfg, only_session=args.only_session)
        combined = transcriber.find_combined(cfg, session_id)
        print(f"録音停止: {session_id}")
        if combined:
            print(f"文字起こし: {combined}")

    elif args.command == "status":
        st = recorder.status(cfg)
        if args.quiet:
            sys.exit(0 if st else 1)
        from scriba.meeting import watch

        print(f"自動録音: {'有効' if watch.running_pid(cfg) else '無効'}")
        if not st:
            print("停止中")
        else:
            m, s = divmod(st["elapsed_sec"], 60)
            print(f"録音中: {st['session_id']}（{st['mode']}）")
            print(f"経過: {m}分{s}秒 / チャンク: {st['chunks']} / 文字起こし済み: {st['transcribed']}")
        unexported = export.list_unexported(cfg)
        if unexported:
            print(f"未転送 {len(unexported)} 件（scriba export <id> --project <案件>）")

    elif args.command == "transcribe":
        if args.all:
            sessions = sorted(p.name for p in cfg.sessions_dir.iterdir() if p.is_dir()) if cfg.sessions_dir.exists() else []
        elif args.session:
            sessions = [args.session]
        else:
            print("セッションIDか --all を指定してください", file=sys.stderr)
            sys.exit(1)
        total = 0
        for sid in sessions:
            if not cfg.session_dir(sid).exists():
                print(f"セッションが見つかりません: {sid}", file=sys.stderr)
                sys.exit(1)
            total += transcriber.transcribe_session(cfg, sid)
        print(f"完了: {total}チャンク処理")

    elif args.command == "merge":
        if not cfg.session_dir(args.session).exists():
            print(f"セッションが見つかりません: {args.session}", file=sys.stderr)
            sys.exit(1)
        until_sec = args.until * 60 if args.until is not None else None
        only_tracks = None if args.track == "both" else {args.track}
        combined = transcriber.merge_session(cfg, args.session, until_sec=until_sec, only_tracks=only_tracks)
        print(f"再生成: {combined}")

    elif args.command == "title":
        sid = _resolve_session(cfg, args.session)
        meta_file = cfg.session_dir(sid) / "meta.json"
        if not meta_file.exists():
            print(f"セッションが見つかりません: {sid}", file=sys.stderr)
            sys.exit(1)
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        old_combined = transcriber.find_combined(cfg, sid)
        meta["title"] = args.title
        meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        if old_combined and old_combined.exists():
            new_name = transcriber.combined_filename(cfg, sid)
            new_combined = old_combined.parent / new_name
            if old_combined != new_combined:
                old_combined.rename(new_combined)
        print(f"会議名を設定: {sid} → {args.title}")

    elif args.command == "export":
        _export(cfg, args.session, args.project)

    elif args.command == "enrich":
        sid = _resolve_session(cfg, args.session)
        if not cfg.session_dir(sid).exists():
            print(f"セッションが見つかりません: {sid}", file=sys.stderr)
            sys.exit(1)
        # calendar再照合
        meta_file = cfg.session_dir(sid) / "meta.json"
        meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
        started = meta.get("started_at", "")
        start_time = datetime.fromisoformat(started) if started else datetime.now()
        events = calendar.load_events(cfg, start_time)
        if events:
            if started:
                result = enrich.match_event(events, start_time)
                if result["match"] == "exact":
                    meta["enrich"] = result["event"]
                    meta["title"] = result["event"].get("subject", "")
                    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(f"照合: {result['event']['subject']}")
                elif result["match"] == "ambiguous":
                    print("複数の予定が見つかりました:")
                    for i, ev in enumerate(result["candidates"], 1):
                        print(f"  {i}. {ev['subject']}")
                    print("scriba title で手動設定してください")
                    sys.exit(0)
                else:
                    print("該当する予定はありません")
                    sys.exit(0)
        # enrich実行
        result = enrich.enrich_session(cfg, sid)
        if result and result.get("path"):
            print(f"更新: {result['path']}")
            fm = result["frontmatter"]
            if fm.get("project"):
                print(f"プロジェクト: {fm['project']}")
            if fm.get("organization"):
                print(f"組織: {fm['organization']}")
        else:
            print("enrich情報がありません（カレンダーに該当予定なし）")

    elif args.command == "discard":
        st = recorder.status(cfg)
        recording = st and (args.session is None or args.session == st["session_id"])
        target = st["session_id"] if recording else (args.session or "最新セッション")
        if not args.yes and sys.stdin.isatty():
            label = "録音中の" if recording else ""
            ans = input(f"{label}{target} を削除します。よろしいですか？ [y/N] ")
            if ans.strip().lower() not in ("y", "yes"):
                print("キャンセルしました")
                return
        sid = recorder.discard(cfg, args.session)
        print(f"破棄: {sid}")

    elif args.command == "view":
        if args.serve:
            server.serve(cfg, args.port)
        else:
            out = render.generate(cfg)
            print(f"生成: {out}")
            subprocess.run(["open", str(out)])

    elif args.command == "dict":
        dic = dictionary.load(cfg.dictionary_path)
        prompt = dic.build_prompt(cfg.model)
        if args.action == "show":
            print(f"辞書: {cfg.dictionary_path}")
            print(f"用語: {len(dic.terms)}件 / 置換: {len(dic.replacements)}件")
            if prompt:
                label = "認識ヒント" if cfg.model.startswith("haas-") else "initial-prompt"
                print(f"{label}: {prompt}")
        verdict, msg = dictionary.validate_prompt(prompt, cfg.model)
        mark = {"ok": "OK", "warn": "警告", "block": "NG"}[verdict]
        print(f"[{mark}] {msg}")
        if verdict == "block":
            sys.exit(1)

    elif args.command == "cleanup":
        removed = recorder.cleanup(cfg)
        if removed:
            for r in removed:
                print(f"削除: {r}")
        else:
            print("削除対象なし")

    elif args.command == "watch":
        _watch(cfg, args.action)

    elif args.command == "worker":
        from scriba.transcription import worker

        worker.run(cfg, args.session)

    elif args.command == "record":
        from scriba.recording import capture

        capture.run(cfg, args.session, args.mic)
