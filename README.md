# AI Store Robot

AI Store Robot is a prototype system to automate a small village general store using AI, computer vision, and robotics.

The goal of this project is to build a smart assistant that can:

- Detect when a customer enters the store
- Greet the customer using voice
- Understand customer requests
- Check product availability
- Record small credit purchases (village store style)
- Eventually move to shelves and deliver items

## Current Features

- Camera system using OpenCV
- Human detection
- Voice greeting system
- Modular architecture for AI components

## Project Structure
ai-store-robot
│
├── camera/ Camera streaming
├── vision/ Person detection
├── voice/ Speech recognition & voice output
├── ai/ AI conversation engine
├── robot/ Robot movement control
├── database/ Store data and customer records
├── utils/ Configurations
│
└── main.py Entry point

## Technologies

- Python
- OpenCV
- SpeechRecognition
- pyttsx3
- Computer Vision
- AI automation

## Future Roadmap

- Face recognition for regular customers
- Product detection without barcode
- Voice-based ordering
- Small credit ledger automation
- Autonomous robot for item delivery

## Author

Chandra
