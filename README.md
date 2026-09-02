<div align="center">

# Clara

### Talk to AI like a real person.

A **fully offline** voice conversation bot. No API keys. No cloud. No data leaves your machine.

Clara listens, responds, and you can interrupt her mid-sentence — just like talking to a real person.

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Moonshine](https://img.shields.io/badge/Moonshine-Voice-FF6B35?style=flat-square)](https://github.com/nickcoutsos/moonshine-voice)
[![Kokoro](https://img.shields.io/badge/Kokoro-TTS-9B59B6?style=flat-square)](https://github.com/thewh1teagle/kokoro-onnx)
[![Gemma](https://img.shields.io/badge/Gemma-4-4285F4?style=flat-square&logo=google&logoColor=white)](https://ai.google.dev/gemma)
[![License](https://img.shields.io/badge/License-MIT-00C853?style=flat-square)](LICENSE)

</div>

---

## Why Clara?

Most voice assistants require internet, API keys, and send your conversations to the cloud. Clara is different. Everything runs on your hardware. Your voice data never leaves your machine.

> "The best AI is the one that doesn't need a server."

---

## Features

### Full-Duplex Conversation

Talk and listen simultaneously. Clara detects when you start speaking while she's still talking — and stops immediately. No waiting for her to finish. Just interrupt naturally, like a real conversation.

### Fully Offline

No API keys. No subscriptions. No telemetry. Clara runs entirely on your local machine using open-source models: Moonshine for speech recognition, Gemma for language, Kokoro for voice.

### Streaming Response

Clara starts speaking before she finishes thinking. Her reply streams token-by-token, gets split into sentences, and each sentence synthesizes while the previous one plays. Perceived latency stays low.

### Dual Interface

Run Clara in the terminal for a lightweight experience, or launch the PyQt6 GUI with an audio-reactive waveform visualization, chat bubbles, and a glowing mic indicator.

### Configurable Persona

Edit `SYSTEM_PROMPT` in `config.py` to change Clara's personality, language style, or behavior. She's as flexible as you need her to be.

### And more

- **Sentence-level pipelining** — next sentence synthesizes while current one plays
- **Barge-in** — interrupt mid-sentence, both LLM and TTS stop instantly
- **Multi-turn memory** — Clara remembers the conversation within a session
- **VAD built-in** — Moonshine handles voice activity detection, no separate VAD needed
- **Lightweight** — no heavy frameworks, just Python + ONNX

---

## Quick Start

### Prerequisites

- Python 3.10+
- `moonshine-voice` and `kokoro-onnx` installed
- `llama-server` running with Gemma on `http://localhost:8081`
- `aplay` (ALSA utils) for audio playback

### Run it

```bash
git clone https://github.com/uxlabspk/Clara.git
cd Clara
pip install -r requirements.txt
```

Place Kokoro model files in the `tts/` directory:
- `kokoro-v1.0.fp16.onnx` (GPU) or `kokoro-v1.0.int8.onnx` (CPU)
- `voices-v1.0.bin`

**Terminal mode:**
```bash
python main.py
```

**GUI mode:**
```bash
python run_gui.py
```

> **Use headphones** for your first test. Without them, speaker output can leak into the mic and trigger false barge-ins.

---

## How it works

```
You speak
    ↓
MicTranscriber        Moonshine VAD detects speech, streams partial transcripts
    ↓
Gemma (llama-server)  Generates response token-by-token via SSE
    ↓
Sentence splitter     Buffers tokens, yields complete sentences
    ↓
Kokoro TTS            Synthesizes sentences in a parallel thread
    ↓
aplay                 Interruptible playback to speaker
```

**Barge-in flow:** You start talking → `on_text` fires → `stop_flag` set → LLM stream aborts + `aplay` killed → Clara listens again.

**Pipelining:** A bounded queue (maxsize=2) overlaps synthesis of sentence N+1 with playback of sentence N.

---

## Tech Stack

| Layer | Tech |
|-------|------|
| STT | **Moonshine Voice** — VAD + STT with partial transcripts |
| LLM | **Gemma 4 E2B** via llama-server — streaming SSE |
| TTS | **Kokoro ONNX** — fast local synthesis |
| GUI | **PyQt6** — audio-reactive waveform, chat bubbles |
| Playback | **aplay** (ALSA) — interruptible subprocess |

---

## Project Structure

```
Clara/
├── main.py          Bot class + CLI entry point
├── config.py        All configuration (LLM, TTS, STT)
├── llm.py           LLM streaming client (llama-server SSE)
├── tts.py           TTS synthesis + interruptible playback pipeline
├── gui.py           PyQt6 GUI with waveform visualization
├── run_gui.py       GUI launcher
├── tts/             Kokoro model files + test script
└── requirements.txt
```

---

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

---

## Contributing

Clara is early. Contributions welcome.

1. Fork it
2. Create a branch (`git checkout -b feat/my-thing`)
3. Commit (`git commit -m 'Add my thing'`)
4. Push (`git push origin feat/my-thing`)
5. Open a PR

---

## License

MIT — do whatever you want with it.

---

**If Clara saves you from yet another cloud subscription, give it a star.**

It helps others find it, and tells me this is worth continuing.

[⭐ Star this repo](https://github.com/uxlabspk/Clara/stargazers)
