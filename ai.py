# FILENAME: ai.py (Version that loads system prompt from O3.txt)

import json
import os
import sys
import serial
import time
from llama_cpp import Llama

# --- SETTINGS ---
USE_ARDUINO = True
SYSTEM_PROMPT_FILE = "/home/asher/private/O3.txt" # --- NEW: Define the prompt file name here

# --- Class for a quiet launch ---
class SuppressStderr:
    def __enter__(self):
        self.original_stderr = sys.stderr
        self.devnull = open(os.devnull, 'w')
        sys.stderr = self.devnull
    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stderr = self.original_stderr
        self.devnull.close()

# --- Global constants ---
HISTORY_FILE = "conversation_history.json"
model_path = "/home/asher/.lmstudio/models/lmstudio-community/gemma-3-1b-it-GGUF/gemma-3-1b-it-Q4_K_M.gguf"

# --- Serial Port Configuration ---
SERIAL_PORT = '/dev/ttyACM0' 
BAUD_RATE = 9600
ser = None 

# --- THIS IS THE ONLY FUNCTION THAT HAS CHANGED ---
def load_history():
    """
    Loads conversation history if it exists. If not, it loads the system 
    prompt from the O3.txt file to start a new conversation.
    """
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            print("Loading previous conversation history...")
            return json.load(f)
    else:
        # No history exists, so we create a new one starting with the system prompt
        try:
            print(f"No history found. Loading system prompt from '{SYSTEM_PROMPT_FILE}'...")
            # 'encoding="utf-8"' is important for special characters
            with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
                system_prompt_content = f.read()
            
            # Return the starting message list
            return [
                {
                    "role": "system",
                    "content": system_prompt_content
                }
            ]
        except FileNotFoundError:
            print("--- FATAL ERROR ---")
            print(f"System prompt file '{SYSTEM_PROMPT_FILE}' was not found!")
            print(f"Please make sure '{SYSTEM_PROMPT_FILE}' is in the same directory as this script.")
            sys.exit(1) # Exit the script because it can't work without the prompt
        except Exception as e:
            print(f"--- FATAL ERROR ---")
            print(f"An error occurred while reading the prompt file: {e}")
            sys.exit(1)


def main():
    global ser
    
    if USE_ARDUINO:
        try:
            print("--- Arduino Connection ---")
            print(f"Attempting to connect on port: {SERIAL_PORT}")
            ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            time.sleep(2) 
            print("Arduino connection successful.")
            print("--------------------------")
        except serial.SerialException as e:
            print(f"!!! ARDUINO FAILED TO CONNECT: {e}")
            ser = None

    try:
        print("Loading model...")
        with SuppressStderr():
            llm = Llama(model_path=model_path, n_ctx=32768, n_threads=8, n_gpu_layers=0, verbose=False)
        print("Model loaded successfully.")
    except Exception as e:
        print(f"Error loading model: {e}")
        exit()

    # --- This now calls our new, smarter function ---
    messages = load_history()
    
    generation_params = {"max_tokens": 2048, "stop": ["<|eot_id|>"], "stream": True, "mirostat_mode": 2, "mirostat_tau": 7.5, "mirostat_eta": 0.1, "repeat_penalty": 1.15, "presence_penalty": -0.1, "frequency_penalty": 0.1, "top_k": 50, "seed": -1}
    print("\n--- Chat with the Guide ---")

    while True:
        user_input = input("You: ")
        if user_input.lower() in ["quit", "exit"]: break

        if ser:
            try:
                user_question_clean = user_input.strip().replace('\n', ' ')
                user_question_to_send = f"USER:{user_question_clean}\n"
                ser.write(user_question_to_send.encode('utf-8'))
            except serial.SerialException as e:
                print(f"--- (Error sending user question: {e}) ---")

        messages.append({"role": "user", "content": user_input})
        response_stream = llm.create_chat_completion(messages=messages, **generation_params)
        assistant_response_full = ""
        print("Guide: ", end="", flush=True)

        for chunk in response_stream:
            delta = chunk['choices'][0]['delta']
            if "content" in delta:
                text_chunk = delta["content"]
                print(text_chunk, end="", flush=True)
                assistant_response_full += text_chunk
        print()

        messages.append({"role": "assistant", "content": assistant_response_full.strip()})
        
        if ser:
            try:
                gemma_response_clean = assistant_response_full.strip().replace('\n', ' ')
                gemma_response_to_send = f"GEMMA:{gemma_response_clean}\n"
                print(f"--- [Sending to Arduino: {len(gemma_response_to_send)} bytes] ---")
                ser.write(gemma_response_to_send.encode('utf-8'))
            except serial.SerialException as e:
                print(f"--- (Error sending Gemma response: {e}) ---")
        
        save_history(messages)

    if ser:
        ser.close()
        print("--- Arduino connection closed. ---")

def save_history(messages):
    """Saves the conversation history to the JSON file."""
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(messages, f, indent=4)
    except Exception as e:
        print(f"Error saving history: {e}")

if __name__ == "__main__":
    main()
