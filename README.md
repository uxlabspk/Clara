# English Practice Bot (full-duplex, offline)

Pipeline: Mic → `MicTranscriber` (moonshine-voice: VAD + STT built in)
→ Gemma 4 E2B via llama-server → Kokoro (TTS) → Speaker

## Setup

1. `llama-server` should already be running with Gemma on `http://localhost:8081`.

2. Put `kokoro-v1.0.fp16.onnx` and `voices-v1.0.bin` in this directory
   (or update paths in `config.py`).

3. Install dependencies (you already have `moonshine-voice` and `kokoro-onnx`,
   this just adds the couple of extras):
   ```bash
   pip install -r requirements.txt
   ```

4. **Use headphones for your first tests.** Without them, the bot's speaker
   output leaks into the mic and can falsely trigger barge-in.

5. Run it:
   ```bash
   python main.py
   ```

## How it works

- `moonshine_voice.MicTranscriber` owns the microphone entirely — it does
  its own capture, VAD, and segmentation, and calls back:
  - `on_text(text)` — fires continuously with the partial transcript while
    it hears live speech.
  - `on_line(line)` — fires once when an utterance is finalized.
- We use `on_line` to know when you've finished a turn, and send that text
  to Gemma.
- We use `on_text` as the **barge-in signal**: if it fires while the bot is
  in the SPEAKING state, that means you're talking over it, so we set an
  interrupt flag.
- The interrupt flag is checked by both `llm.py` (aborts the streaming
  generation) and `tts.py` (aborts audio playback mid-sentence) — so both
  stop almost immediately.
- Gemma's reply streams token-by-token from `llama-server` and is split into
  sentences as they complete, so Kokoro can start speaking the first
  sentence before Gemma has finished generating the rest of the reply —
  this is what keeps the perceived latency low.

## Tuning

- If Moonshine's VAD is too twitchy or slow to finalize lines, check its
  own configuration methods (`update_interval()`, etc. — see the
  moonshine-voice docs) rather than tuning here; we're not running a
  separate VAD anymore.
- If barge-in triggers on the bot's own voice: use headphones. If that's
  not possible, we can add a "don't listen to on_text while unless it
  persists for N callbacks" debounce — ask and I'll add it.
- `SYSTEM_PROMPT` in `config.py` controls Gemma's conversational style —
  edit freely.
- If Kokoro playback lags: the fp16 model is GPU-oriented; a quantized/int8
  Kokoro build may run faster on CPU.

## Known limitations / next steps

- Terminal-only for now (GUI planned later).
- No acoustic echo cancellation — headphones recommended for reliable
  barge-in.
- If you barge in mid-sentence, the partial bot reply is not saved to
  conversation history as if it were fully said.
- No wake word — always listening once running.
