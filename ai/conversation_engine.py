from voice.text_to_speech import speak
from voice.speech_to_text import listen
from ai.brain import ask_ai

order = []

products = ["coke","sprite","thums up","chips","biscuit"]

def start_conversation():

    speak("Welcome to the store. What would you like?")

    while True:

        text = listen()

        if not text:
            speak("Sorry I didn't hear that.")
            continue

        text = text.lower()

        print("Customer:", text)

        if "done" in text or "that's all" in text:

            if len(order) == 0:
                speak("You did not order anything.")
                continue

            speak("Your order is")

            for item in order:
                speak(item)

            speak("Thank you for visiting.")
            break

        found_items = []

        for product in products:
            if product in text:
                found_items.append(product)

        if len(found_items) > 0:

            for item in found_items:
                order.append(item)
                speak(f"{item} added")

            speak("Anything else?")

        else:

            response = ask_ai(text)
            speak(response)