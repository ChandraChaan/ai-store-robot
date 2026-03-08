from voice.speech_to_text import listen
from voice.text_to_speech import speak
from ai.brain import ask_ai
from utils import config
import time

def start_conversation():

    config.conversation_active = True

    speak("Em kavali? Nenu meeku sahayam cheyadaniki ikkadunnanu")

    while config.customer_inside:

        print("Listening...")

        text = listen()

        if not text:
            continue

        print("Customer:", text)

        response = ask_ai(text)

        speak(response)

    config.conversation_active = False