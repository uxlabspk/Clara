"""
Talks to llama-server's OpenAI-compatible streaming endpoint and yields
text sentence-by-sentence (so TTS can start before generation finishes).
"""
import json
import re
import requests

import config as cfg
import web

# Split right after . ! or ? — do NOT require trailing whitespace, since a
# streamed delta can end exactly on the punctuation with the next word's
# space arriving in a later chunk. Requiring \s+ here delayed every sentence
# flush by one extra network round-trip.
_SENTENCE_END = re.compile(r"(?<=[.!?])")

_TOOLS = [{
    "type": "function",
    "function": {
        "name": "search_web",
        "description": "Search the web for current or factual information.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A concise web search query.",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}]

history = [{"role": "system", "content": cfg.SYSTEM_PROMPT}]


def reset_history():
    global history
    history = [{"role": "system", "content": cfg.SYSTEM_PROMPT}]


def _stream_request(messages, stop_flag):
    """Yield streamed text and the completed tool calls from one request."""
    payload = {
        "model": cfg.LLAMA_MODEL_NAME,
        "messages": messages,
        "max_tokens": cfg.MAX_TOKENS,
        "temperature": cfg.TEMPERATURE,
        "stream": True,
    }
    if cfg.ENABLE_WEB_SEARCH:
        payload["tools"] = _TOOLS
        payload["tool_choice"] = "auto"

    content = ""
    tool_calls = {}
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
                delta = json.loads(data)["choices"][0]["delta"]
            except (KeyError, IndexError, json.JSONDecodeError):
                continue

            text = delta.get("content") or ""
            if text:
                content += text
                yield text, None

            for call in delta.get("tool_calls") or []:
                index = call.get("index", 0)
                current = tool_calls.setdefault(index, {
                    "id": "",
                    "type": "function",
                    "function": {"name": "", "arguments": ""},
                })
                current["id"] += call.get("id") or ""
                function = call.get("function") or {}
                current["function"]["name"] += function.get("name") or ""
                current["function"]["arguments"] += function.get("arguments") or ""

    yield "", list(tool_calls.values())


def stream_reply(user_text: str, stop_flag):
    """
    Sends user_text, appends to history, and yields sentence chunks as
    they become available. stop_flag is a callable: if it returns True,
    generation is abandoned early (used for barge-in).

    Yields (sentence: str, is_final: bool).
    Appends the full assistant reply to `history` once done (or interrupted).
    """
    history.append({"role": "user", "content": user_text})

    messages = list(history)
    buffer = ""
    full_reply = ""

    for _ in range(3):
        round_content = ""
        requested_tools = None
        for delta, calls in _stream_request(messages, stop_flag):
            round_content += delta
            if calls is not None:
                requested_tools = calls
            if delta:
                buffer += delta
                full_reply += delta
                parts = _SENTENCE_END.split(buffer)
                if len(parts) > 1:
                    *complete, buffer = parts
                    buffer = buffer.lstrip()
                    for sentence in complete:
                        sentence = sentence.strip()
                        if sentence:
                            yield sentence, False

        if not requested_tools:
            break

        messages.append({
            "role": "assistant",
            "content": round_content or None,
            "tool_calls": requested_tools,
        })
        for call in requested_tools:
            try:
                arguments = json.loads(call["function"]["arguments"] or "{}")
                result = web.search(arguments["query"])
            except (KeyError, TypeError, json.JSONDecodeError):
                result = "Search failed: invalid search arguments."
            if not result:
                result = "No search results were found."
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": result,
            })

    # flush whatever's left (final partial sentence, or everything if interrupted)
    if buffer.strip():
        yield buffer.strip(), True
    else:
        yield "", True

    history.append({"role": "assistant", "content": full_reply})