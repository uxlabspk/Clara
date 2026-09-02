"""
Talks to llama-server's OpenAI-compatible streaming endpoint and yields
text sentence-by-sentence (so TTS can start before generation finishes).
"""
import json
import re
import requests

import config as cfg

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

history = [{"role": "system", "content": cfg.SYSTEM_PROMPT}]


def reset_history():
    global history
    history = [{"role": "system", "content": cfg.SYSTEM_PROMPT}]


def stream_reply(user_text: str, stop_flag):
    """
    Sends user_text, appends to history, and yields sentence chunks as
    they become available. stop_flag is a callable: if it returns True,
    generation is abandoned early (used for barge-in).

    Yields (sentence: str, is_final: bool).
    Appends the full assistant reply to `history` once done (or interrupted).
    """
    history.append({"role": "user", "content": user_text})

    payload = {
        "model": cfg.LLAMA_MODEL_NAME,
        "messages": history,
        "max_tokens": cfg.MAX_TOKENS,
        "temperature": cfg.TEMPERATURE,
        "stream": True,
    }

    buffer = ""
    full_reply = ""

    with requests.post(cfg.LLAMA_SERVER_URL, json=payload, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines(decode_unicode=True):
            if stop_flag():
                break
            if not line or not line.startswith("data: "):
                continue
            data = line[len("data: "):]
            if data.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(data)
                delta = chunk["choices"][0]["delta"].get("content", "")
            except (KeyError, json.JSONDecodeError, IndexError):
                continue

            if not delta:
                continue

            buffer += delta
            full_reply += delta

            # flush complete sentences as they form
            parts = _SENTENCE_END.split(buffer)
            if len(parts) > 1:
                *complete, buffer = parts
                for sentence in complete:
                    sentence = sentence.strip()
                    if sentence:
                        yield sentence, False

    # flush whatever's left (final partial sentence, or everything if interrupted)
    if buffer.strip():
        yield buffer.strip(), True
    else:
        yield "", True

    history.append({"role": "assistant", "content": full_reply})
