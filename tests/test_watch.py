from scriba.meeting.watch import Detector


def _run(detector, steps):
    """(秒, マイク使用, 録音中セッション) の列を流し、出た指示を (秒, 指示) で返す。"""
    actions = []
    for t, mic, session in steps:
        action = detector.step(t, mic, session)
        if action:
            actions.append((t, action))
    return actions


def test_starts_after_mic_in_use_and_stops_after_release():
    d = Detector(start_sec=4, stop_sec=10)
    steps = [(0, True, None), (2, True, None), (4, True, None), (6, True, "s1"),
             (100, False, "s1"), (105, False, "s1"), (110, False, "s1")]
    assert _run(d, steps) == [(4, "start"), (110, "stop")]


def test_short_mic_blip_is_ignored():
    """マイクの短い使用・短い中断（ミュート等）では開始も停止もしない。"""
    d = Detector(start_sec=4, stop_sec=10)
    assert _run(d, [(0, True, None), (2, False, None), (8, False, None)]) == []
    d = Detector(start_sec=4, stop_sec=10)
    steps = [(0, True, None), (4, True, None), (6, True, "s1"), (20, False, "s1"), (25, True, "s1"), (40, True, "s1")]
    assert _run(d, steps) == [(4, "start")]


def test_manual_stop_during_meeting_is_not_restarted():
    d = Detector(start_sec=4, stop_sec=10)
    steps = [(0, True, None), (4, True, None), (6, True, "s1"), (30, True, None), (60, True, None),
             (100, False, None), (110, False, None)]
    assert _run(d, steps) == [(4, "start")]


def test_back_to_back_meetings_get_separate_sessions():
    """前の会議の stop が state を解放する前に次の会議が始まっても、新しく開始する。"""
    d = Detector(start_sec=4, stop_sec=10)
    steps = [(0, True, None), (4, True, None), (6, True, "s1"),
             (100, False, "s1"), (110, False, "s1"),       # 会議1の終了 → stop
             (112, True, "s1"), (116, True, "s1"),         # stop 中に会議2が始まる
             (118, True, "s2"), (300, False, "s2"), (310, False, "s2")]
    assert _run(d, steps) == [(4, "start"), (110, "stop"), (116, "start"), (310, "stop")]


def test_manual_session_in_meeting_is_stopped_at_end():
    """会議中に手で始めた録音も、会議の終わりに止める。"""
    d = Detector(start_sec=4, stop_sec=10)
    steps = [(0, True, "m1"), (4, True, "m1"), (100, False, "m1"), (110, False, "m1")]
    assert _run(d, steps) == [(110, "stop")]


def test_recording_outside_meeting_is_left_alone():
    d = Detector(start_sec=4, stop_sec=10)
    assert _run(d, [(0, False, "m1"), (100, False, "m1")]) == []
