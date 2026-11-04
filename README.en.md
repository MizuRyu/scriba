<p align="center">
  <img src="images/scriba-icon.png" width="128" alt="scriba icon">
</p>

# scriba

[日本語](README.md)

scriba is a macOS CLI that records online meetings entirely on your Mac and transcribes them every two minutes.

It records the other participants and you on separate tracks and merges them into a time-ordered transcript labeled `[相手]` (them) and `[自分]` (you). It matches each recording against your calendar, adds the meeting title and project, and hands the transcript to the folder your notes app or summarizer reads.

[![Demo of transcription, auto recording, and calendar matching](images/scriba-demo-ja.gif)](images/scriba-demo-ja.mp4)

*A product movie made with fictional meeting data (Japanese). Click to open the 24-second video with music.*

## Features

- **Stays on your Mac.** Recording and transcription run locally; neither audio nor text is sent anywhere. The network is used only for the first model download and, if you configure one, a calendar URL.
- **Two speakers.** The other participants come from system audio via BlackHole, you come from the microphone, and both are merged in time order.
- **Readable during the meeting.** Each two-minute chunk is transcribed as soon as it is complete.
- **Hands-free recording.** Recording starts when a meeting app begins using the microphone and stops when it releases it. Recordings shorter than 60 seconds (a waiting room or a meeting joined by mistake) are discarded; change this with `min_keep_sec`.
- **Titles and projects.** Meeting titles come from iCalendar (.ics / URL) or JSON events; organization and project are inferred from email domains and keywords and written as frontmatter. Classification is rule-based; no LLM is involved.
- **A dictionary that grows.** Proper nouns are passed as recognition hints, recurring misrecognitions are replaced, and boilerplate hallucinations are dropped. Past meetings can be rebuilt after you edit the dictionary.
- **A viewer to read and fix.** A monochrome HTML viewer to read transcripts, edit the dictionary and settings, and pick a project to export to.
- **Keeps going.** A missing calendar or a failed voice detection never stops recording. Silence notifications, a forgotten-recording timeout (3 hours by default), and an automatic stop on no speech are built in.

## Example output

```text
---
title: 【ACME】定例 7/6
date: 2026-07-06
start: "09:15"
end: "10:00"
organization: ACME
project: acme
source_session: 20260706-091500
---

[00:00] [相手]
では、先週の課題から確認していきます

[00:21] [自分]
設計書の更新は昨日終わりました
```

*Output from a fictional meeting. Times are elapsed from the start of recording. Once a project is determined, the file is exported to a per-project folder such as `transcript/acme/`.*

![Meeting list with titles, times, and character counts](images/viewer-sessions.png)

![Meeting detail with both speakers in time order](images/viewer-session.png)

*The actual viewer rendered with fictional meeting data.*

## Requirements

An Apple Silicon Mac with macOS 14.2 or later. Japanese meetings are the primary target; the UI and messages are in Japanese.

| Requirement | Used for |
|---|---|
| [uv](https://docs.astral.sh/uv/) | Installation and running transcription and voice detection in separate processes |
| [BlackHole 2ch](https://github.com/ExistentialAudio/BlackHole) | Virtual device that routes meeting audio to the recorder |
| [switchaudio-osx](https://github.com/deweller/switchaudio-osx) | Switching the output device only while recording |
| ffmpeg | Whisper models |

## Speech recognition models

The default is Haas-ja-v1.0 Q4_K (speech.cpp). Set `model` to a Whisper model name to use mlx-whisper instead.

| Model | Time for 120 s of audio | Peak memory |
|---|---:|---:|
| Haas-ja-v1.0 Q4_K (default) | 3.1 s | 479 MiB |
| Whisper large-v3-turbo | 14.7 s | 2,564 MiB |
| Whisper large-v3 | 41.3 s | 5,095 MiB |

*Measured on an M4 with 32 GiB. Times are the median of three runs, including model loading and voice detection. Accuracy was not compared.*

Heavy dependencies (speech.cpp, mlx-whisper, Silero VAD) are not scriba dependencies; they run in separate processes. See [ADR-003](docs/adr/003-heavy-deps-in-subprocess.md).

## Install

```sh
brew install blackhole-2ch switchaudio-osx ffmpeg
uv tool install --editable .
scriba setup-model   # downloads and verifies the Haas binary and weights (about 353 MB)
```

Then create a Multi-Output Device (BlackHole 2ch + your headphones) in Audio MIDI Setup and select it as the speaker in your meeting app. scriba switches the system output only while recording. On an English macOS, set the device names in `~/scriba/config.toml`:

```toml
multi_output_device = "Multi-Output Device"
device_mic = "External Microphone"   # only used with capture_mic = true
```

Microphone permission is inherited from the app that launches scriba. Run it from an app that has microphone access, such as Raycast; launched from a terminal without it, scriba may silently record nothing.

## Usage

```sh
scriba watch on       # enable auto recording (start/stop with meetings)
scriba start          # start recording manually
scriba stop           # stop and transcribe the rest
scriba status         # recording state and number of unexported meetings
scriba view --serve   # open the viewer
```

| When | Do |
|---|---|
| An unscheduled meeting has no project | `scriba export <id> --project <name>` or pick one in the viewer; the same recurring meeting is classified automatically next time |
| Misrecognitions stand out | Add them to the dictionary and run `scriba merge <id>` |
| The meeting started late and has no title | `scriba title <id> <title>` |

Raycast Script Commands are in [raycast/](raycast/). The full command and configuration reference is in [docs/usage.md](docs/usage.md) (Japanese).

## Limitations

- Multiple remote speakers are not distinguished; the system track is treated as one speaker.
- No summaries or minutes formatting. The transcript is raw material for downstream tools.
- One Mac, one user, one recording at a time.

## Development

```sh
nix develop   # optional
just setup
just test
just verify   # ruff + pytest + Gitleaks
```

See [docs/development.md](docs/development.md) and [CONTRIBUTING.md](CONTRIBUTING.md). Follow your organization's and the meeting's rules on recording and transcription. Data handling is described in [SECURITY.md](.github/SECURITY.md).

## License

[MIT](LICENSE). Licenses of the software used at runtime: [docs/third-party-licenses.md](docs/third-party-licenses.md).
