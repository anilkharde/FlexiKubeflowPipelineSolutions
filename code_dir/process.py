import random
import time

class CustomProcess():
    def __init__(self, process_time):
        super().__init__()
        self.sleep_time = process_time

    def run(self):
        while True:
            random_number = random.randint(1, 100)
            print("In custom process run...")
            print(f"Generated random number: {random_number}")
            time.sleep(self.process_time)