# real_time_transcriber.py

import speech_recognition as sr
import time

def main():
    """
    Continuously listens for speech and transcribes it in real-time.
    """
    # 1. Initialize the Recognizer
    recognizer = sr.Recognizer()
    
    # 2. Get the Microphone
    microphone = sr.Microphone()

    # 3. Define the Callback Function
    # This function will be called every time speech is recognized.
    def on_speech_recognized(recognizer, audio_data):
        print(">>> Recognizing...")
        try:
            # Use Google's free web speech API to recognize the audio
            text = recognizer.recognize_google(audio_data)
            
            # Print the recognized text
            # The `end=' '` and `flush=True` make it appear on one line.
            print(f"{text} ", end='', flush=True)

        except sr.UnknownValueError:
            # This error means the API couldn't understand the audio
            print("[Could not understand audio]", end='', flush=True)
        except sr.RequestError as e:
            # This error means there was a problem with the API request
            print(f"\n[API Error: {e}]")

    # 4. Adjust for Ambient Noise
    with microphone as source:
        print("Please wait. Calibrating microphone for ambient noise...")
        recognizer.adjust_for_ambient_noise(source, duration=1)
        print("Calibration complete. You can start speaking now.")

    # 5. Start Listening in the Background
    # This is a non-blocking call that starts a new thread.
    stop_listening = recognizer.listen_in_background(microphone, on_speech_recognized)
    
    # 6. Keep the Main Thread Alive
    # The background thread will do all the work. We just need to keep the
    # script running until the user wants to stop.
    print("--- Listening continuously. Press Ctrl+C to stop. ---")
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n--- Stopping the listener. ---")
        stop_listening(wait_for_stop=False)
        print("Listener stopped. Goodbye!")

# Standard Python entry point
if __name__ == "__main__":
    main()
