import random
import time

class CustomProcess():
    def __init__(self, process_time):
        """
        Initialize the CustomProcess class with the given process time.
        
        Args:
            process_time (int): The time in seconds the process will sleep between iterations.
        """
        super().__init__()
        self.sleep_time = process_time

    def run(self):
        """
        Run the custom process logic. This method generates a random number,
        prints it, and then sleeps for the specified amount of time.
        """
        # Generate a random number between 1 and 100
        random_number = random.randint(1, 100)
        print("In custom process run...")
        print(f"Generated random number: {random_number}")
        # Sleep for the specified amount of time
        time.sleep(self.sleep_time)
