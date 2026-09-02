"""
Kokoro TTS + interruptible playback.

NOTE: sounddevice/PortAudio produces silent (but error-free) output on this
machine, likely due to JACK interfering with PortAudio's ALSA routing.
`aplay` reliably works, so we shell out to it instead of using PortAudio
for playback. Synthesis still uses kokoro-onnx directly.
"""
import os
import subprocess
import tempfile
import threading
import time
import numpy as np
import soundfile as sf

import config as cfg

_kokoro = None
_playback_lock = threading.Lock()

OUTPUT_SAMPLE_RATE = 48000


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


def synthesize(text: str):
    """Returns (samples, sample_rate)."""
    if _kokoro is None:
        load()
    samples, sample_rate = _kokoro.create(
        text, voice=cfg.KOKORO_VOICE, speed=cfg.KOKORO_SPEED, lang=cfg.KOKORO_LANG
    )
    return samples, sample_rate


def speak_interruptible(text: str, stop_flag) -> bool:
    """
    Synthesizes and plays `text` via aplay. Polls stop_flag() periodically
    and kills playback early if it returns True (barge-in).

    Returns True if playback completed fully, False if interrupted.
    """
    samples, sample_rate = synthesize(text)
    samples = _resample(samples, sample_rate, OUTPUT_SAMPLE_RATE)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    sf.write(wav_path, samples, OUTPUT_SAMPLE_RATE)

    with _playback_lock:
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
                time.sleep(0.05)
        finally:
            os.unlink(wav_path)

    return True
