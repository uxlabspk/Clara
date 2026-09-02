# Clara — Offline Voice Conversation Bot

**Full-duplex, offline voice bot for natural conversation practice.**

Talk to Clara like a real person. She listens, responds, and you can interrupt her mid-sentence — all running locally on your machine.

[![Stars](https://img.shields.io/github/stars/uxlabspk/Clara?style=social)](https://github.com/uxlabspk/Clara)

---

## Features

- **Full-duplex conversation** — interrupt Clara mid-sentence with natural barge-in
- **Fully offline** — no API keys, no cloud, no data leaves your machine
- **Streaming TTS** — she starts speaking before she finishes thinking
- **Sentence-level pipelining** — next sentence synthesizes while current one plays
- **Dual interface** — terminal CLI or PyQt6 GUI with audio-reactive waveform
- **Configurable persona** — edit `SYSTEM_PROMPT` in `config.py`

## Architecture

```
Microphone
    ↓
MicTranscriber (moonshine-voice)   VAD + STT, partial & final transcripts
    ↓
Gemma 4 E2B (llama-server)         Streaming token generation via SSE
    ↓
Sentence splitter                   Buffers tokens, yields complete sentences
    ↓
Kokoro TTS (ONNX)                  Synthesizes sentences in parallel thread
    ↓
aplay (ALSA)                       Interruptible playback
    ↓
Speaker
```

**Barge-in flow:** When you start talking while Clara speaks, `on_text` partial transcripts fire → `stop_flag` is set → LLM stream aborts + `aplay` process killed → Clara listens again.

**Pipelining:** A bounded queue (maxsize=2) overlaps TTS synthesis of sentence N+1 with playback of sentence N, keeping perceived latency low.

## Quick Start

### Prerequisites

- Python 3.10+
- `moonshine-voice` and `kokoro-onnx` installed
- `llama-server` running with Gemma on `http://localhost:8081`
- `aplay` (ALSA utils) for audio playback

### Install

```bash
pip install -r requirements.txt
```

Place Kokoro model files in the `tts/` directory:
- `kokoro-v1.0.fp16.onnx` (GPU) or `kokoro-v1.0.int8.onnx` (CPU)
- `voices-v1.0.bin`

### Run

**Terminal mode:**
```bash
python main.py
```

**GUI mode:**
```bash
python run_gui.py
```

> **Use headphones** for your first test. Without them, speaker output can leak into the mic and trigger false barge-ins.

## Configuration

All settings live in `config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `LLAMA_SERVER_URL` | `http://localhost:8081` | LLM endpoint |
| `SYSTEM_PROMPT` | Clara persona | Bot personality and behavior |
| `MAX_TOKENS` | `512` | Max response length |
| `TEMPERATURE` | `0.7` | Response creativity |
| `KOKORO_VOICE` | `af_heart` | Voice style |
| `KOKORO_SPEED` | `1.0` | Speech rate |
| `KOKORO_LANG` | `a` | Language |

## Tuning

- **VAD too twitchy/slow** — adjust `moonshine_voice.MicTranscriber` methods (e.g., `update_interval()`). See moonshine-voice docs.
- **False barge-ins** — use headphones. Alternatively, request a debounce filter.
- **TTS latency** — use `kokoro-v1.0.int8.onnx` for faster CPU inference (fp16 is GPU-oriented).
- **Response style** — edit `SYSTEM_PROMPT` in `config.py`.

## Known Limitations

- No acoustic echo cancellation — headphones recommended for reliable barge-in
- Barge-in discards partial bot responses (not saved to conversation history)
- No wake word — always listening once started
- `aplay` used instead of PortAudio to avoid JACK interference (documented in `tts.py`)

## Project Structure

```
├── main.py          Core Bot class + CLI entry point
├── config.py        All configuration (LLM, TTS, STT)
├── llm.py           LLM streaming client (llama-server SSE)
├── tts.py           TTS synthesis + interruptible playback pipeline
├── gui.py           PyQt6 GUI with waveform visualization
├── run_gui.py       GUI launcher
├── tts/             Kokoro model files + test script
└── requirements.txt
```

## Contributing

Contributions welcome. Open an issue or submit a PR.

## License

MIT

---

**If you find Clara useful, please star the repo** — it helps others discover it.
