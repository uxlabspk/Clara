"""
English conversation practice bot — full-duplex, offline.

Pipeline: Mic -> MicTranscriber (moonshine-voice: VAD+STT built in)
          -> Gemma (llama-server, streamed) -> Kokoro (TTS) -> Speaker

Barge-in: MicTranscriber keeps listening in the background even while
the bot is speaking. Any live partial transcript (on_text) during
SPEAKING is treated as the user interrupting.

Run: python main.py
"""
import sys
import threading
import time
import queue

from moonshine_voice import MicTranscriber

import config as cfg
import llm
import tts

DEBUG_TIMING = True  # set False once you're happy with latency


class Bot:
    def __init__(self):
        self.state = "LISTENING"  # LISTENING | SPEAKING
        self.state_lock = threading.Lock()
        self.interrupt_flag = threading.Event()

        self.line_queue: "queue.Queue[str]" = queue.Queue()

        self.mic = (
            MicTranscriber()
            .language(cfg.MOONSHINE_LANGUAGE)
            .on_text(self._on_text)
            .on_line(self._on_line)
        )

    # ---- MicTranscriber callbacks (run on Moonshine's background thread) ----

    def _on_text(self, text: str):
        """Fires continuously with partial transcript while speech is heard."""
        with self.state_lock:
            speaking = self.state == "SPEAKING"
        if speaking and text.strip():
            self.interrupt_flag.set()
        else:
            # live feedback while user is talking to us
            print(f"\r  ...{text}", end="", flush=True)

    def _on_line(self, line):
        """Fires once an utterance is finalized."""
        text = line.text.strip()
        if text:
            if DEBUG_TIMING:
                print(f"\n  [t=0.00s] STT finalized")
            self.line_queue.put(text)

    # ---- main loop ----

    def stop_flag(self) -> bool:
        return self.interrupt_flag.is_set()

    def run(self):
        print("Loading models (first run downloads/caches them, be patient)...")
        self.mic.load()
        tts.load()
        self.mic.start()
        print("Ready. Speak into your mic. Press Ctrl+C to quit.\n")
        print("[listening]")

        try:
            while True:
                user_text = self.line_queue.get()  # blocks until a finalized line arrives
                print(f"\rYou: {user_text}" + " " * 20)

                with self.state_lock:
                    self.state = "SPEAKING"
                self.interrupt_flag.clear()

                interrupted = self._speak_reply(user_text)

                with self.state_lock:
                    self.state = "LISTENING"

                if interrupted:
                    print("[interrupted — listening again]")
                    time.sleep(0.05)
                else:
                    print("[listening]")

        except KeyboardInterrupt:
            pass
        finally:
            self.mic.stop()

    def _speak_reply(self, user_text: str) -> bool:
        """
        Streams sentences from the LLM directly into tts.speak_stream, which
        pipelines synthesis (kokoro) and playback (aplay) internally so that
        sentence N+1 is being synthesized while sentence N is still playing.
        """
        printed = []

        def sentences():
            for sentence, is_final in llm.stream_reply(user_text, self.stop_flag):
                if not sentence:
                    continue
                printed.append(sentence)
                print(f"\nBot: {' '.join(printed)}", end="", flush=True)
                yield sentence

        print("Bot: ", end="", flush=True)
        completed = tts.speak_stream(sentences(), self.stop_flag)
        print()
        return not completed


if __name__ == "__main__":
    try:
        Bot().run()
    except KeyboardInterrupt:
        pass
    print("\nBye!")
    sys.exit(0)