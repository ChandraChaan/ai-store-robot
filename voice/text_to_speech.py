import subprocess

def speak(text):
    try:
        print("AI Speaking:", text)
        subprocess.call(["say", "-r", "160", text])
    except Exception as e:
        print("Speech error:", e)