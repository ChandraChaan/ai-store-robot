import requests

def ask_ai(text):

    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "phi3",
            "prompt": f"""
You are a shop assistant.

Products available:
coke, sprite, thums up, chips, biscuit

User said: {text}

Reply shortly like a shopkeeper.
""",
            "stream": False
        }
    )

    result = response.json()["response"]

    return result