# FILENAME: ai.py (Fully Optional Arguments Version)

import json
import os
import sys
import serial
import time
import argparse
from llama_cpp import Llama

# --- SETTINGS ---
USE_ARDUINO = True

# --- Class for a quiet launch ---
class SuppressStderr:
    def __enter__(self): self.original_stderr = sys.stderr; self.devnull = open(os.devnull, 'w'); sys.stderr = self.devnull
    def __exit__(self, exc_type, exc_val, exc_tb): sys.stderr = self.original_stderr; self.devnull.close()

# --- Global constants ---
model_path = "/home/asher/.lmstudio/models/lmstudio-community/gemma-3-1b-it-GGUF/gemma-3-1b-it-Q4_K_M.gguf"

# --- Serial Port Configuration ---
SERIAL_PORT = '/dev/ttyACM0' 
BAUD_RATE = 9600
ser = None 

# --- File handling functions ---

def load_history(history_path):
    """Loads history from the provided path. Handles missing file gracefully."""
    print("--- Loading Context ---")
    if history_path is None:
        print("--> No --history file specified. Session will be ephemeral.")
        return None
        
    if os.path.exists(history_path):
        try:
            with open(history_path, "r") as f:
                print(f"--> Resuming conversation from:\n    '{history_path}'")
                return json.load(f)
        except Exception as e:
            print(f"--> WARNING: History file found but was unreadable: {e}. Starting new conversation.")
            return None
    else:
        print(f"--> History file not found. A new file will be created at:\n    '{history_path}'")
        return None

# --- THIS FUNCTION IS UPDATED ---
def get_system_prompt(prompt_path):
    """Loads a system prompt. If no path is given or file is not found, returns an empty prompt."""
    # Case 1: No prompt file was specified at all.
    if prompt_path is None:
        print("--> No --prompt file specified. Using a default empty system prompt.")
        return [{"role": "system", "content": ""}]

    # Case 2: A prompt file was specified, try to read it.
    try:
        print(f"--> Loading system prompt from:\n    '{prompt_path}'")
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt_content = f.read()
        return [{"role": "system", "content": system_prompt_content}]
    except FileNotFoundError:
        # If the specified file doesn't exist, it's a warning, not an error.
        print(f"--> WARNING: Prompt file not found at '{prompt_path}'.")
        print("--> Using a default empty system prompt instead.")
        return [{"role": "system", "content": ""}]
    except Exception as e:
        # For any other errors, also default to an empty prompt.
        print(f"--> WARNING: Could not read prompt file due to an error: {e}")
        print("--> Using a default empty system prompt instead.")
        return [{"role": "system", "content": ""}]


def save_history(messages, history_path):
    """Saves history. Does nothing if no path was provided."""
    if history_path is None:
        return
    try:
        with open(history_path, "w") as f:
            json.dump(messages, f, indent=4)
    except Exception as e:
        print(f"Error saving history to '{history_path}': {e}")


def main():
    # --- ARGUMENT PARSER IS UPDATED ---
    parser = argparse.ArgumentParser(
        description="An AI chat terminal with Arduino integration.",
        epilog="Example: python3 ai.py --prompt O3.txt --history my_chat.json"
    )
    # Both arguments are now optional (required=False is default)
    parser.add_argument(
        '-p', '--prompt',
        type=str,
        help="Path to the system prompt text file (e.g., O3.txt). If omitted, a blank prompt is used."
    )
    parser.add_argument(
        '-H', '--history',
        type=str,
        help="Path to conversation history JSON file. If omitted, the session is not saved."
    )
    args = parser.parse_args()

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
        print("--- Loading Model ---")
        with SuppressStderr():
            llm = Llama(model_path=model_path, n_ctx=32768, n_threads=8, n_gpu_layers=0, verbose=False)
        print("Model loaded successfully.")
    except Exception as e:
        print(f"Error loading model: {e}")
        exit()

    messages = load_history(args.history)
    if messages is None:
        messages = get_system_prompt(args.prompt)
    
    generation_params = {"max_tokens": 2048, "stop": ["<|eot_id|>"], "stream": True, "mirostat_mode": 2, "mirostat_tau": 7.5, "mirostat_eta": 0.1, "repeat_penalty": 1.15, "presence_penalty": -0.1, "frequency_penalty": 0.1, "top_k": 50, "seed": -1}
    print("\n--- Chat with the AI ---")

    # The rest of the main loop is unchanged
    while True:
        user_input = input("You: ")
        if user_input.lower() in ["quit", "exit"]: break
        if ser:
            try:
                user_question_clean = user_input.strip().replace('\n', ' ')
                user_question_to_send = f"USER:{user_question_clean}\n"
                ser.write(user_question_to_send.encode('utf-8'))
            except serial.SerialException as e: print(f"--- (Error sending user question: {e}) ---")
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
            except serial.SerialException as e: print(f"--- (Error sending Gemma response: {e}) ---")
        save_history(messages, args.history)

    if ser:
        ser.close()
        print("--- Arduino connection closed. ---")

if __name__ == "__main__":
    main()