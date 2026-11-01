import json
import re
import wave

import pytest
from conftest import write_transcript

from scriba.transcription import transcriber

TIME_HEAD = re.compile(r"^\[\d{2}:\d{2}\]$")


def _combined(cfg, session_id):
    path = transcriber.find_combined(cfg, session_id)
    assert path is not None, "combined file not found"
    return path.read_text(encoding="utf-8")


def test_single_track_heading_per_chunk(cfg):
    """単一トラック: チャンク境界ごとに [MM:SS] 見出しが1つ出る。"""
    sid = "s1"
    sdir = cfg.session_dir(sid)
    write_transcript(sdir, "teams_000", [
        {"start": 0.0, "text": "こんにちは"},
        {"start": 5.0, "text": "続きです"},
    ])
    write_transcript(sdir, "teams_001", [
        {"start": 1.0, "text": "次のチャンク"},
    ])
    transcriber.merge_session(cfg, sid)
    text = _combined(cfg, sid)
    lines = [ln for ln in text.splitlines() if ln]
    headings = [ln for ln in lines if TIME_HEAD.match(ln)]
    # 2チャンク → 見出し2つ、話者ラベルは付かない
    assert len(headings) == 2
    assert headings[0] == "[00:00]"
    # chunk_duration=120s, idx=1 の start=1.0 → 121s = [02:01]
    assert headings[1] == "[02:01]"
    assert "[相手]" not in text
    assert "[自分]" not in text


def test_multi_track_speaker_labels_and_blocks(cfg):
    """複数トラック: 話者ラベル付き、話者交代でブロック分割。"""
    sid = "s2"
    sdir = cfg.session_dir(sid)
    write_transcript(sdir, "teams_000", [
        {"start": 0.0, "text": "相手A"},
        {"start": 10.0, "text": "相手B"},
    ])
    write_transcript(sdir, "mic_000", [
        {"start": 5.0, "text": "自分X"},
    ])
    transcriber.merge_session(cfg, sid)
    text = _combined(cfg, sid)
    # 時刻順: 相手A(0) -> 自分X(5) -> 相手B(10) の3ブロック
    heads = [ln for ln in text.splitlines() if ln.startswith("[")]
    assert heads[0].endswith("[相手]")
    assert heads[1].endswith("[自分]")
    assert heads[2].endswith("[相手]")
    assert len(heads) == 3


def test_replacements_applied(cfg):
    """置換辞書が combined.txt に適用される。"""
    sid = "s3"
    sdir = cfg.session_dir(sid)
    write_transcript(sdir, "teams_000", [{"start": 0.0, "text": "設計ショーの件"}])
    (cfg.dictionary_path).write_text(
        "replacements:\n  設計ショー: 設計書\n", encoding="utf-8"
    )
    transcriber.merge_session(cfg, sid)
    text = _combined(cfg, sid)
    assert "設計書" in text
    assert "設計ショー" not in text


def test_filter_removes_matching_segments(cfg):
    """フィルタ一致セグメント（句読点付き一致含む）を除去し combined から消す。"""
    sid = "f1"
    sdir = cfg.session_dir(sid)
    write_transcript(sdir, "teams_000", [
        {"start": 0.0, "text": "本題です"},
        {"start": 5.0, "text": "ご視聴ありがとうございました。"},  # 末尾句読点付き
        {"start": 10.0, "text": "はい"},  # DEFAULT_FILTERS
        {"start": 15.0, "text": "続きます"},
    ])
    transcriber.merge_session(cfg, sid)
    text = _combined(cfg, sid)
    assert "本題です" in text
    assert "続きます" in text
    assert "ご視聴ありがとうございました" not in text
    assert "はい" not in text


def test_filter_no_partial_match(cfg):
    """部分一致では除去しない（「はい」を含む長文は残る）。"""
    sid = "f2"
    sdir = cfg.session_dir(sid)
    write_transcript(sdir, "teams_000", [
        {"start": 0.0, "text": "はい、承知しました"},
    ])
    transcriber.merge_session(cfg, sid)
    assert "はい、承知しました" in _combined(cfg, sid)


def test_filter_hallucination_compounds(cfg):
    """定型句の連結・前置き付きも除去し、定型語を含む通常発話は残す。"""
    sid = "f5"
    sdir = cfg.session_dir(sid)
    write_transcript(sdir, "mic_000", [
        {"start": 0.0, "text": "このように、私はあなたを愛しています。"},
        {"start": 5.0, "text": "はい、では、次の動画でお会いしましょう。"},
        {"start": 7.0, "text": "はい、では次の動画でお会いしましょう。"},
        {"start": 10.0, "text": "私は、私の動画を撮影しています。"},
        {"start": 12.0, "text": "このように、このように、この"},  # 末尾で途切れた繰り返し
        {"start": 15.0, "text": "全体の構成としてはこのようになっています"},
        {"start": 20.0, "text": "では"},
    ])
    transcriber.merge_session(cfg, sid)
    text = _combined(cfg, sid)
    assert "愛しています" not in text
    assert "次の動画" not in text
    assert "撮影しています" not in text
    assert "このように、この" not in text
    assert "このようになっています" in text
    assert "では" in text


def test_merge_keeps_frontmatter(cfg):
    """merge で本文を再生成しても enrich の frontmatter は残る。"""
    sid = "fm1"
    sdir = cfg.session_dir(sid)
    write_transcript(sdir, "teams_000", [{"start": 0.0, "text": "本題です"}])
    transcriber.merge_session(cfg, sid)
    combined = transcriber.find_combined(cfg, sid)
    combined.write_text("---\ntitle: 定例\n---\n\n古い本文\n", encoding="utf-8")
    transcriber.merge_session(cfg, sid)
    text = transcriber.find_combined(cfg, sid).read_text(encoding="utf-8")
    assert text.startswith("---\ntitle: 定例\n---\n\n")
    assert "本題です" in text
    assert "古い本文" not in text


def test_filters_disabled(cfg):
    """filters_enabled=false なら除去しない。"""
    cfg.filters_enabled = False
    sid = "f3"
    sdir = cfg.session_dir(sid)
    write_transcript(sdir, "teams_000", [
        {"start": 0.0, "text": "はい"},
    ])
    transcriber.merge_session(cfg, sid)
    assert "はい" in _combined(cfg, sid)


def test_filter_union_with_dict_yaml(cfg):
    """dict.yaml の filters と DEFAULT_FILTERS の和集合が適用される。"""
    sid = "f4"
    sdir = cfg.session_dir(sid)
    write_transcript(sdir, "teams_000", [
        {"start": 0.0, "text": "了解です"},  # dict.yaml 由来
        {"start": 5.0, "text": "はい"},       # DEFAULT_FILTERS 由来
        {"start": 10.0, "text": "本題"},
    ])
    cfg.dictionary_path.write_text("filters:\n  - 了解です\n", encoding="utf-8")
    transcriber.merge_session(cfg, sid)
    text = _combined(cfg, sid)
    assert "了解です" not in text
    assert "はい" not in text
    assert "本題" in text


def test_until_sec_trims_tail(cfg):
    """until_sec 以降に開始するセグメントを除外する。"""
    sid = "u1"
    sdir = cfg.session_dir(sid)
    write_transcript(sdir, "teams_000", [
        {"start": 10.0, "text": "会議中"},
        {"start": 100.0, "text": "余分な末尾"},
    ])
    transcriber.merge_session(cfg, sid, until_sec=60.0)
    text = _combined(cfg, sid)
    assert "会議中" in text
    assert "余分な末尾" not in text


def test_filter_does_not_touch_source_json(cfg):
    """フィルタは combined.txt のみに作用し transcripts/*.json は不変。"""
    sid = "f5"
    sdir = cfg.session_dir(sid)
    write_transcript(sdir, "teams_000", [
        {"start": 0.0, "text": "はい"},
        {"start": 5.0, "text": "本題"},
    ])
    src = sdir / "transcripts" / "teams_000.json"
    before = src.read_text(encoding="utf-8")
    transcriber.merge_session(cfg, sid)
    assert src.read_text(encoding="utf-8") == before


def test_dedupe_consecutive_same_text(cfg):
    """正規化後同一の連続セグメントは最初の1つだけ残す。"""
    sid = "d1"
    sdir = cfg.session_dir(sid)
    write_transcript(sdir, "teams_000", [
        {"start": 0.0, "text": "ありがとうございました"},
        {"start": 5.0, "text": "ありがとうございました"},
        {"start": 10.0, "text": "ありがとうございました"},
    ])
    transcriber.merge_session(cfg, sid)
    text = _combined(cfg, sid)
    assert text.count("ありがとうございました") == 1


def test_dedupe_not_across_intervening_text(cfg):
    """間に別発話を挟む同一文は畳まれない。"""
    sid = "d2"
    sdir = cfg.session_dir(sid)
    write_transcript(sdir, "teams_000", [
        {"start": 0.0, "text": "同じ話"},
        {"start": 5.0, "text": "別の話"},
        {"start": 10.0, "text": "同じ話"},
    ])
    transcriber.merge_session(cfg, sid)
    text = _combined(cfg, sid)
    assert text.count("同じ話") == 2


def test_dedupe_across_tracks(cfg):
    """トラックをまたいだ連続重複も畳む（2トラックのエコー対策）。"""
    sid = "d3"
    sdir = cfg.session_dir(sid)
    write_transcript(sdir, "teams_000", [{"start": 0.0, "text": "エコー発話"}])
    write_transcript(sdir, "mic_000", [{"start": 1.0, "text": "エコー発話"}])
    transcriber.merge_session(cfg, sid)
    text = _combined(cfg, sid)
    assert text.count("エコー発話") == 1


def test_dedupe_normalizes_punctuation(cfg):
    """句読点違いも正規化一致で畳まれる。"""
    sid = "d4"
    sdir = cfg.session_dir(sid)
    write_transcript(sdir, "teams_000", [
        {"start": 0.0, "text": "ありがとうございました。"},
        {"start": 5.0, "text": "ありがとうございました"},
    ])
    transcriber.merge_session(cfg, sid)
    text = _combined(cfg, sid)
    # 正規化一致で2つ目は畳まれ、1つ目（句読点付き）だけ残る
    assert text.count("ありがとうございました") == 1


def test_fmt_time():
    assert transcriber._fmt_time(0) == "[00:00]"
    assert transcriber._fmt_time(61) == "[01:01]"
    assert transcriber._fmt_time(3661) == "[1:01:01]"


# --- combined_filename / find_combined / merge ファイル名 ---

def _write_meta(cfg, session_id, meta):
    sdir = cfg.session_dir(session_id)
    sdir.mkdir(parents=True, exist_ok=True)
    import json as _json
    (sdir / "meta.json").write_text(_json.dumps(meta, ensure_ascii=False), encoding="utf-8")


def test_combined_filename_with_title(cfg):
    """title ありで yymmdd_hhmm_タイトル.txt を返す。"""
    sid = "cf1"
    _write_meta(cfg, sid, {"started_at": "2026-07-03T14:05:49", "title": "定例MTG"})
    assert transcriber.combined_filename(cfg, sid) == "260703_1405_定例MTG.txt"


def test_combined_filename_without_title(cfg):
    """title なしで yymmdd_hhmm.txt を返す。"""
    sid = "cf2"
    _write_meta(cfg, sid, {"started_at": "2026-07-03T14:05:49"})
    assert transcriber.combined_filename(cfg, sid) == "260703_1405.txt"


def test_combined_filename_bad_chars_replaced(cfg):
    """タイトル中のファイル名禁止文字はハイフンに置換。"""
    sid = "cf3"
    _write_meta(cfg, sid, {"started_at": "2026-07-03T14:05:49", "title": 'A/B:C*D?"E'})
    name = transcriber.combined_filename(cfg, sid)
    assert name == "260703_1405_A-B-C-D--E.txt"
    for ch in '/\\:*?"<>|':
        assert ch not in name


def test_combined_filename_no_started_at_fallback(cfg):
    """started_at がないとき session_id 先頭12文字をフォールバック。"""
    sid = "20260703-140549"
    _write_meta(cfg, sid, {"title": "会議A"})
    assert transcriber.combined_filename(cfg, sid) == "20260703-140_会議A.txt"


def test_merge_session_generates_titled_filename(cfg):
    """merge_session が yymmdd_hhmm_タイトル.txt を生成する。"""
    sid = "mt1"
    _write_meta(cfg, sid, {"started_at": "2026-07-03T09:00:00", "title": "朝会"})
    write_transcript(cfg.session_dir(sid), "teams_000", [{"start": 0.0, "text": "内容"}])
    combined = transcriber.merge_session(cfg, sid)
    assert combined.name == "260703_0900_朝会.txt"
    assert combined.exists()


def test_merge_session_removes_old_combined(cfg):
    """merge_session 後に旧 combined.txt が残らない。"""
    sid = "mt2"
    _write_meta(cfg, sid, {"started_at": "2026-07-03T09:00:00", "title": "会議"})
    sdir = cfg.session_dir(sid)
    write_transcript(sdir, "teams_000", [{"start": 0.0, "text": "内容"}])
    # 旧ファイルを作成
    (sdir / "transcripts" / "combined.txt").write_text("old", encoding="utf-8")
    combined = transcriber.merge_session(cfg, sid)
    assert combined.name == "260703_0900_会議.txt"
    assert not (sdir / "transcripts" / "combined.txt").exists()


def test_find_combined_none_when_empty(cfg):
    """transcripts/ に .txt がないとき None。"""
    sid = "fc1"
    sdir = cfg.session_dir(sid)
    (sdir / "transcripts").mkdir(parents=True, exist_ok=True)
    assert transcriber.find_combined(cfg, sid) is None


def test_find_combined_ignores_chunk_json_stems(cfg):
    """チャンク JSON と同 stem の .txt は combined とみなさない。"""
    sid = "fc2"
    sdir = cfg.session_dir(sid)
    write_transcript(sdir, "teams_000", [{"start": 0.0, "text": "x"}])
    # teams_000.txt を置いても find_combined は返さない
    (sdir / "transcripts" / "teams_000.txt").write_text("dummy", encoding="utf-8")
    assert transcriber.find_combined(cfg, sid) is None


def test_find_combined_returns_old_name(cfg):
    """旧名 combined.txt でも見つかる。"""
    sid = "fc3"
    sdir = cfg.session_dir(sid)
    (sdir / "transcripts").mkdir(parents=True, exist_ok=True)
    target = sdir / "transcripts" / "combined.txt"
    target.write_text("content", encoding="utf-8")
    assert transcriber.find_combined(cfg, sid) == target


def test_merge_drops_mic_segments_outside_vad(cfg):
    """micはVAD発話区間と重なるセグメントだけ残す。VAD結果のないteamsはそのまま。"""
    sid = "v1"
    sdir = cfg.session_dir(sid)
    write_transcript(sdir, "mic_000", [
        {"start": 0.0, "end": 3.0, "text": "自分の発言です"},
        {"start": 30.0, "end": 60.0, "text": "発話区間の外の幻聴"},
    ])
    write_transcript(sdir, "teams_000", [{"start": 40.0, "end": 45.0, "text": "相手の発言です"}])
    (sdir / "transcripts" / "mic_000.vad.json").write_text(json.dumps([[0.5, 2.0]]), encoding="utf-8")
    transcriber.merge_session(cfg, sid)
    text = _combined(cfg, sid)
    assert "自分の発言です" in text
    assert "幻聴" not in text
    assert "相手の発言です" in text


def _silent_wav(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\0\0" * 16000)


def test_mic_chunk_without_speech_skips_whisper(cfg, monkeypatch):
    """発話区間のないmicチャンクはWhisperを呼ばず、空の結果を残す。"""
    cfg.model = "mlx-community/whisper-large-v3-turbo"
    wav = cfg.session_dir("v2") / "chunks" / "mic_000.wav"
    _silent_wav(wav)
    monkeypatch.setattr(transcriber.vad, "speech_intervals", lambda w: [])
    monkeypatch.setattr(transcriber.subprocess, "run", lambda *a, **k: pytest.fail("Whisperが呼ばれた"))
    entry = transcriber.transcribe_chunk(cfg, "v2", wav)
    out = cfg.session_dir("v2") / "transcripts"
    assert entry["no_speech_skipped"] is True
    assert json.loads((out / "mic_000.json").read_text())["segments"] == []
    assert json.loads((out / "mic_000.vad.json").read_text()) == []
    assert transcriber.pending_chunks(cfg, "v2") == []


def test_vad_failure_still_transcribes(cfg, monkeypatch):
    """VADが失敗してもWhisperは実行する。"""
    cfg.model = "mlx-community/whisper-large-v3-turbo"
    wav = cfg.session_dir("v3") / "chunks" / "mic_000.wav"
    _silent_wav(wav)
    calls = []

    def fail(w):
        raise OSError("uv not found")

    monkeypatch.setattr(transcriber.vad, "speech_intervals", fail)
    monkeypatch.setattr(transcriber.subprocess, "run", lambda cmd, **k: calls.append(cmd))
    entry = transcriber.transcribe_chunk(cfg, "v3", wav)
    assert calls and entry["no_speech_skipped"] is False
    assert not (cfg.session_dir("v3") / "transcripts" / "mic_000.vad.json").exists()
