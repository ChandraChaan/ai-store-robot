import whisper
import sounddevice as sd
import numpy as np
import tempfile
import scipy.io.wavfile as wav

model = whisper.load_model("base")

def listen():

    print("Listening...")

    samplerate = 16000
    duration = 5

    recording = sd.rec(int(duration * samplerate),
                       samplerate=samplerate,
                       channels=1)

    sd.wait()

    temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)

    wav.write(temp_file.name, samplerate, recording)

    result = model.transcribe(temp_file.name)

    text = result["text"].lower()

    print("Customer said:", text)

    return text