"""
Kokoro TTS + interruptible playback.

NOTE: sounddevice/PortAudio produces silent (but error-free) output on this
machine, likely due to JACK interfering with PortAudio's ALSA routing.
`aplay` reliably works, so we shell out to it instead of using PortAudio
for playback. Synthesis still uses kokoro-onnx directly.

Synthesis (kokoro.create) and playback (aplay) are roughly equal in cost
(~0.7-1.3s synth for ~1.5-2s of audio, then ~1.5-2s to actually play it).
Running them serially per-sentence means every sentence pays both costs
back-to-back. speak_stream() below pipelines them: while sentence N plays,
sentence N+1 is already being synthesized in the background.
"""
import os
import subprocess
import tempfile
import threading
import time
import queue
import numpy as np
import soundfile as sf

import config as cfg

_kokoro = None
OUTPUT_SAMPLE_RATE = 48000
DEBUG_TIMING = True


def _resample(samples: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    if orig_sr == target_sr:
        return samples
    duration = len(samples) / orig_sr
    n_target = int(round(duration * target_sr))
    orig_idx = np.linspace(0, len(samples) - 1, num=len(samples))
    target_idx = np.linspace(0, len(samples) - 1, num=n_target)
    return np.interp(target_idx, orig_idx, samples).astype(np.float32)


def load():
    global _kokoro
    from kokoro_onnx import Kokoro
    _kokoro = Kokoro(cfg.KOKORO_MODEL_PATH, cfg.KOKORO_VOICES_PATH)
    return _kokoro


def _synthesize_wav(text: str) -> str:
    """Synthesizes text, resamples, writes to a temp WAV, returns its path."""
    if _kokoro is None:
        load()
    t0 = time.monotonic()
    samples, sample_rate = _kokoro.create(
        text, voice=cfg.KOKORO_VOICE, speed=cfg.KOKORO_SPEED, lang=cfg.KOKORO_LANG
    )
    samples = _resample(samples, sample_rate, OUTPUT_SAMPLE_RATE)
    if DEBUG_TIMING:
        dur = len(samples) / OUTPUT_SAMPLE_RATE
        print(f"\n    [synth: {time.monotonic()-t0:.2f}s for {dur:.2f}s audio "
              f"RTF={(time.monotonic()-t0)/dur:.2f}] {text!r}")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    sf.write(wav_path, samples, OUTPUT_SAMPLE_RATE)
    return wav_path


def _play_wav(wav_path: str, stop_flag) -> bool:
    """Plays a WAV via aplay, killable via stop_flag. Returns False if interrupted."""
    t0 = time.monotonic()
    proc = subprocess.Popen(
        ["aplay", "-q", wav_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        while proc.poll() is None:
            if stop_flag():
                proc.terminate()
                try:
                    proc.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return False
            time.sleep(0.03)
    finally:
        os.unlink(wav_path)
    if DEBUG_TIMING:
        print(f"    [play: {time.monotonic()-t0:.2f}s]")
    return True


def speak_stream(sentences, stop_flag):
    """
    Consumes an iterable/generator of sentence strings. Synthesizes them
    on a background thread while playing them back-to-back on the calling
    thread, so synthesis of sentence N+1 overlaps with playback of N.

    `sentences` can be a generator that itself takes time to produce items
    (e.g. streaming from an LLM) — this function pulls from it lazily.

    Returns True if all sentences played fully, False if interrupted partway.
    """
    wav_queue: "queue.Queue[str | None]" = queue.Queue(maxsize=2)  # small buffer, not unbounded

    def synthesizer():
        try:
            for sentence in sentences:
                if not sentence or stop_flag():
                    break
                wav_path = _synthesize_wav(sentence)
                wav_queue.put(wav_path)
                if stop_flag():
                    break
        finally:
            wav_queue.put(None)  # sentinel

    synth_thread = threading.Thread(target=synthesizer, daemon=True)
    synth_thread.start()

    completed = True
    while True:
        wav_path = wav_queue.get()
        if wav_path is None:
            break
        if stop_flag():
            os.unlink(wav_path)
            completed = False
            break
        if not _play_wav(wav_path, stop_flag):
            completed = False
            break

    synth_thread.join(timeout=2)
    return completed