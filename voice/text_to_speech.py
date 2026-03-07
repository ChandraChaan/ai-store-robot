import subprocess
import threading


def speak(text):
    """
    Speak text using macOS built-in 'say' command
    This is very stable on Mac
    """

    def run():
        try:
            print("AI Speaking:", text)
            subprocess.run(["say", text])
        except Exception as e:
            print("Speech error:", e)

    threading.Thread(target=run, daemon=True).start()