"""
Talks to llama-server's OpenAI-compatible streaming endpoint and yields
text sentence-by-sentence (so TTS can start before generation finishes).
"""
import json
import re
import requests

import config as cfg
import web

# Keywords that suggest the user wants current/external information
_SEARCH_HINTS = re.compile(
    r"\b(news|latest|today|recent|current|now|this week|this month|this year|"
    r"what(?:'s| is) (?:the |happening|going on)|who is|who won|"
    r"stock|price|score|weather|update|headline)\b",
    re.IGNORECASE,
)

# Split right after . ! or ? — do NOT require trailing whitespace, since a
# streamed delta can end exactly on the punctuation with the next word's
# space arriving in a later chunk. Requiring \s+ here delayed every sentence
# flush by one extra network round-trip.
_SENTENCE_END = re.compile(r"(?<=[.!?])")

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

    # --- web search injection ---
    search_snippet = ""
    if cfg.ENABLE_WEB_SEARCH and _SEARCH_HINTS.search(user_text):
        search_snippet = web.search(user_text)

    messages = list(history)
    if search_snippet:
        # Prepend search results as system context so the LLM can use them.
        messages.insert(1, {
            "role": "system",
            "content": (
                "Web search returned the following results. "
                "Use them if relevant, ignore if not.\n\n" + search_snippet
            ),
        })

    payload = {
        "model": cfg.LLAMA_MODEL_NAME,
        "messages": messages,
        "max_tokens": cfg.MAX_TOKENS,
        "temperature": cfg.TEMPERATURE,
        "stream": True,
    }

    buffer = ""
    full_reply = ""

    # stream=True + iter_lines/iter_content only avoids buffering the whole
    # body if the server itself flushes chunks promptly; llama-server does
    # this correctly over SSE, so this should yield incrementally.
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

            # flush complete sentences (and any leading whitespace of the
            # next one) as soon as terminal punctuation appears
            parts = _SENTENCE_END.split(buffer)
            if len(parts) > 1:
                *complete, buffer = parts
                buffer = buffer.lstrip()
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