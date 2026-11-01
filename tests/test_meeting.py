import subprocess

from scriba import notify
from scriba.meeting import detect

PROCESSES = {1: ("com.microsoft.teams2.modulehost", 0), 2: ("us.zoom.xos", 1), 3: ("com.apple.Safari", 1)}


def _fake_coreaudio(monkeypatch):
    monkeypatch.setattr(detect, "_process_ids", lambda: list(PROCESSES))
    monkeypatch.setattr(detect, "_bundle_id", lambda obj: PROCESSES[obj][0])

    def get(obj, selector, buf):
        buf.value = PROCESSES[obj][1]
        return True

    monkeypatch.setattr(detect, "_get", get)


def test_only_listed_apps_count(monkeypatch):
    _fake_coreaudio(monkeypatch)
    assert not detect.mic_in_use(["com.microsoft.teams"])
    assert detect.mic_in_use(["com.microsoft.teams", "us.zoom.xos"])
    assert not detect.mic_in_use([])


def test_notify_passes_text_as_arguments(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    notify.notify("Scriba", '「"引用"」\\ を含む')
    assert calls[0][0:2] == ["osascript", "-e"]
    assert calls[0][3:] == ["Scriba", '「"引用"」\\ を含む']
    assert '"' not in calls[0][2]
