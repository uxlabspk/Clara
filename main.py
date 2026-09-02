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
        Runs LLM generation and TTS playback concurrently: a producer thread
        pulls sentences from llm.stream_reply as fast as the model emits them
        and puts them on a queue; this (main) thread plays each sentence as
        soon as it's available. This means sentence 2 is already being
        generated while sentence 1 is being spoken, instead of the two
        happening strictly one-after-the-other.

        Returns True if interrupted (barge-in), False if completed normally.
        """
        sentence_queue: "queue.Queue[tuple[str, bool] | None]" = queue.Queue()
        t_start = time.monotonic()

        def producer():
            try:
                for sentence, is_final in llm.stream_reply(user_text, self.stop_flag):
                    if DEBUG_TIMING:
                        print(f"\n  [+{time.monotonic()-t_start:.2f}s] LLM sentence ready: {sentence!r}")
                    sentence_queue.put((sentence, is_final))
                    if self.stop_flag():
                        break
            finally:
                sentence_queue.put(None)  # sentinel: generation done

        producer_thread = threading.Thread(target=producer, daemon=True)
        producer_thread.start()

        interrupted = False
        print("Bot: ", end="", flush=True)
        while True:
            item = sentence_queue.get()
            if item is None:
                break
            sentence, is_final = item
            if self.stop_flag():
                interrupted = True
                break
            if not sentence:
                continue
            print(sentence, end=" ", flush=True)
            if DEBUG_TIMING:
                t_tts_start = time.monotonic()
            completed = tts.speak_interruptible(sentence, self.stop_flag)
            if DEBUG_TIMING:
                print(f"\n  [+{time.monotonic()-t_start:.2f}s] TTS done "
                      f"(took {time.monotonic()-t_tts_start:.2f}s)")
            if not completed:
                interrupted = True
                break
        print()

        if interrupted:
            self.interrupt_flag.set()  # ensure producer thread also stops promptly
        producer_thread.join(timeout=2)
        return interrupted


if __name__ == "__main__":
    try:
        Bot().run()
    except KeyboardInterrupt:
        pass
    print("\nBye!")
    sys.exit(0)