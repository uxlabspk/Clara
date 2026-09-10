"""
Central configuration. Tune these once you see real behavior on your machine.
"""

# ---- STT (moonshine-voice MicTranscriber) ----
MOONSHINE_LANGUAGE = "en"

# ---- Barge-in ----
# moonshine-voice's on_text fires with partial transcripts while it hears
# speech. We treat any such callback while the bot is speaking as barge-in.

# ---- LLM (Gemma via llama-server) ----
LLAMA_SERVER_URL = "http://localhost:8081/v1/chat/completions"
LLAMA_MODEL_NAME = "gemma"           # llama-server usually ignores this but the field is required
MAX_TOKENS = 200                     # keep replies conversational, not essays
TEMPERATURE = 0.8

SYSTEM_PROMPT = (
    "You are Clara, a helpful assistant. Keep replies short and natural, "
    "like real spoken conversation (1-3 sentences). Do not use markdown, "
    "bullet points, or emoji since your reply will be read aloud."
)

# ---- TTS (Kokoro, via kokoro-onnx directly) ----
KOKORO_MODEL_PATH = "tts/kokoro-v1.0.fp16.onnx"
KOKORO_VOICES_PATH = "tts/voices-v1.0.bin"
KOKORO_VOICE = "af_heart"
KOKORO_SPEED = 1.0
KOKORO_LANG = "en-us"
