import json
import os
import sys
import serial
import time
import argparse
from llama_cpp import Llama
import requests
from bs4 import BeautifulSoup
# --- MODIFICATION: Make speech_recognition optional ---
try:
    import speech_recognition as sr
    SPEECH_RECOGNITION_AVAILABLE = True
except ImportError:
    SPEECH_RECOGNITION_AVAILABLE = False


# --- 1. CENTRALIZED CONFIGURATION ---
CONFIG = {
    "model_path": "/home/asher/.lmstudio/models/lmstudio-community/gemma-3-1b-it-GGUF/gemma-3-1b-it-Q4_K_M.gguf",
    "serial_port": '/dev/ttyACM0',
    "baud_rate": 9600,
    "llama_params": {
        "n_ctx": 32768,
        "n_threads": 8,
        "n_gpu_layers": 0,
        "verbose": False
    },
    "creativity_preset": "balanced",
    "generation_params": {
        "focused": {"temperature": 0.4, "top_k": 20, "top_p": 0.9, "repeat_penalty": 1.15, "mirostat_mode": 0},
        "balanced": {"temperature": 0.7, "top_k": 40, "top_p": 0.95, "repeat_penalty": 1.1, "mirostat_mode": 0},
        "creative": {"temperature": 0.85, "top_k": 50, "top_p": 0.95, "repeat_penalty": 1.1, "mirostat_mode": 2, "mirostat_tau": 6.0, "mirostat_eta": 0.1}
    },
    "common_generation_params": {
        "max_tokens": 2048,
        "stop": ["<|eot_id|>"],
        "stream": True,
        "seed": -1
    }
}

# --- Helper Classes (Unchanged) ---
class SuppressStderr:
    def __enter__(self): self.original_stderr = sys.stderr; self.devnull = open(os.devnull, 'w'); sys.stderr = self.devnull
    def __exit__(self, exc_type, exc_val, exc_tb): sys.stderr = self.original_stderr; self.devnull.close()

class SuppressALSAErrors:
    def __enter__(self): self.original_stderr_fd = sys.stderr.fileno(); self.saved_stderr_fd = os.dup(self.original_stderr_fd); self.devnull_fd = os.open(os.devnull, os.O_WRONLY); os.dup2(self.devnull_fd, self.original_stderr_fd)
    def __exit__(self, exc_type, exc_val, exc_tb): os.dup2(self.saved_stderr_fd, self.original_stderr_fd); os.close(self.devnull_fd); os.close(self.saved_stderr_fd)

# --- Helper Functions (Unchanged) ---
def get_latest_news():
    url = "https://en.wikipedia.org/wiki/Portal:Current_events"; headlines = []
    try:
        print("--> Fetching news..."); headers = {'User-Agent': 'Mozilla/5.0'}; response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status(); soup = BeautifulSoup(response.text, 'html.parser')
        news_items = soup.select('div#bodyContent li')
        if not news_items: return "Could not find list items."
        for item in news_items:
            text = item.get_text(strip=True).replace('(pictured)', '').replace('[edit]', '');
            if len(text) > 20: headlines.append(text)
        if headlines: return " | ".join(headlines[:7])
        else: return "Could not find valid headlines."
    except Exception as e: print(f"!!! Error scraping: {e}"); return "Error parsing news."

def load_history(history_path):
    if not history_path or not os.path.exists(history_path): return None
    try:
        with open(history_path, "r") as f: print(f"--> Resuming from: '{history_path}'"); return json.load(f)
    except Exception as e: print(f"--> WARNING: Unreadable history: {e}"); return None

def get_system_prompt(prompt_path):
    if not prompt_path: return [{"role": "system", "content": ""}]
    try:
        with open(prompt_path, "r", encoding="utf-8") as f: print(f"--> Loading prompt: '{prompt_path}'"); return [{"role": "system", "content": f.read()}]
    except Exception: print(f"--> WARNING: Prompt not found or unreadable. Using empty prompt."); return [{"role": "system", "content": ""}]

def save_history(messages, history_path):
    if history_path:
        try:
            with open(history_path, "w") as f: json.dump(messages, f, indent=4)
        except Exception as e: print(f"Error saving history: {e}")

# --- 3. MODULARIZED FUNCTIONS ---
def initialize_llm():
    try:
        print("--- Loading Model ---");
        with SuppressStderr(): llm = Llama(model_path=CONFIG["model_path"], **CONFIG["llama_params"])
        print("Model loaded successfully.")
        return llm
    except Exception as e:
        print(f"!!! FATAL: Error loading model: {e}"); exit()

def initialize_arduino(use_arduino_flag):
    # --- MODIFICATION: Connects only if the flag is True ---
    if not use_arduino_flag:
        return None
    try:
        print("--- Arduino Connection ---")
        ser = serial.Serial(CONFIG["serial_port"], CONFIG["baud_rate"], timeout=1)
        time.sleep(2)
        print("Arduino connection successful."); print("--------------------------")
        return ser
    except serial.SerialException as e:
        print(f"!!! ARDUINO FAILED TO CONNECT: {e}"); return None

def get_user_speech(recognizer, microphone):
    print("You (speak now): ", end="", flush=True)
    try:
        with microphone as source:
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=15)
        print("\r>>> Recognizing...                        ", end="", flush=True)
        user_input = recognizer.recognize_google(audio)
        print(f"\rYou: {user_input}                             ")
        return user_input
    except (sr.WaitTimeoutError, sr.UnknownValueError, sr.RequestError):
        print("\r(Could not understand audio, please try again.)", end="", flush=True)
        return None

def get_user_text():
    user_input = input("You: ")
    return user_input

def send_to_arduino(ser, prefix, text_content):
    if not ser: return
    clean_text = text_content.strip().replace('\n', ' '); CHUNK_SIZE = 200
    try:
        if len(clean_text) <= CHUNK_SIZE:
            ser.write(f"{prefix}:{clean_text}\n".encode('utf-8')); ser.flush()
        else:
            ser.write(f"{prefix}_START:{clean_text[:CHUNK_SIZE]}\n".encode('utf-8')); ser.flush(); time.sleep(0.05)
            for i in range(CHUNK_SIZE, len(clean_text), CHUNK_SIZE):
                next_chunk = clean_text[i:i + CHUNK_SIZE]
                ser.write(f"{prefix}_APPEND:{next_chunk}\n".encode('utf-8')); ser.flush(); time.sleep(0.05)
            ser.write(f"{prefix}_END:\n".encode('utf-8')); ser.flush()
    except serial.SerialException as e:
        print(f"!!! (Error sending to Arduino: {e}) !!!")

def main_loop(args, recognizer=None, microphone=None):
    # --- MODIFICATION: Initialize based on the presence of the --use-arduino flag ---
    ser = initialize_arduino(args.use_arduino)
    llm = initialize_llm()
    messages = load_history(args.history) or get_system_prompt(args.prompt)
    active_params = {**CONFIG['common_generation_params'], **CONFIG['generation_params'][CONFIG['creativity_preset']]}
    print(f"--> Using '{CONFIG['creativity_preset']}' creativity preset.")
    print("\n--- Chat with the AI (type 'news', 'update', 'quit', 'exit', or 'stop') ---")

    while True:
        # --- MODIFICATION: Choose input method based on --use-voice flag ---
        if args.use_voice:
            user_input = get_user_speech(recognizer, microphone)
            if not user_input: continue
        else:
            user_input = get_user_text()

        if not user_input: continue

        lower_input = user_input.lower()
        if lower_input in ["quit", "exit", "stop"]: break
        if lower_input in ["news", "update"]:
            news_string = get_latest_news()
            print(f"News: {news_string}")
            send_to_arduino(ser, "GEMMA", news_string)
            continue

        send_to_arduino(ser, "USER", user_input)
        messages.append({"role": "user", "content": user_input})
        print("AI: Thinking...", end="\r", flush=True)
        response_stream = llm.create_chat_completion(messages=messages, **active_params)
        print("AI: ", end="", flush=True)
        assistant_response_full = ""
        for chunk in response_stream:
            if "content" in (delta := chunk['choices'][0]['delta']):
                text_chunk = delta["content"]
                print(text_chunk, end="", flush=True)
                assistant_response_full += text_chunk
        print()
        messages.append({"role": "assistant", "content": assistant_response_full.strip()})
        send_to_arduino(ser, "GEMMA", assistant_response_full)
        save_history(messages, args.history)

    if ser: ser.close(); print("--- Arduino connection closed. ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="An AI chat terminal with Arduino integration.")
    parser.add_argument('-p', '--prompt', type=str, help="Path to the system prompt text file.")
    parser.add_argument('-H', '--history', type=str, help="Path to conversation history JSON file.")
    # --- MODIFICATION: Flags to ENABLE features instead of disabling them ---
    parser.add_argument('--use-arduino', action='store_true', help="Enable the serial connection to the Arduino.")
    parser.add_argument('--use-voice', action='store_true', help="Enable voice-to-text input using a microphone.")
    args = parser.parse_args()

    # --- MODIFICATION: Main logic is now flipped ---
    try:
        if args.use_voice:
            if not SPEECH_RECOGNITION_AVAILABLE:
                print("!!! The 'speech_recognition' library is not installed.")
                print("!!! Please run 'pip install SpeechRecognition' to use this feature.")
                exit()
            with SuppressALSAErrors():
                try:
                    r = sr.Recognizer()
                    m = sr.Microphone()
                    with m as source:
                        print("Please wait. Calibrating microphone..."); r.adjust_for_ambient_noise(source, duration=1.5); print("Calibration complete.")
                    main_loop(args, recognizer=r, microphone=m)
                except Exception as e:
                    print(f"!!! A microphone could not be initialized: {e}")
                    print("!!! Please check your microphone connection and configuration.")
        else:
            # Default behavior: run with text input
            main_loop(args)
    except KeyboardInterrupt:
        print("\n--- Exiting gracefully ---")
    finally:
        print("\nGoodbye!")
