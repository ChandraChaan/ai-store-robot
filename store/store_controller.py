class StoreController:

    def __init__(self):
        self.customer_inside = False
        self.conversation_active = False

    def customer_entered(self):

        if not self.customer_inside:
            self.customer_inside = True

            speak("Welcome to the store")

            start_conversation()

    def customer_left(self):

        self.customer_inside = False
        self.conversation_active = False

        speak("Thank you, visit again")