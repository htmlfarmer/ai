import json
import os
import sys
import serial
import time
import argparse
from llama_cpp import Llama
import requests
from bs4 import BeautifulSoup
import speech_recognition as sr

# --- SETTINGS ---
USE_ARDUINO = True
model_path = "/home/asher/.lmstudio/models/lmstudio-community/gemma-3-1b-it-GGUF/gemma-3-1b-it-Q4_K_M.gguf"
SERIAL_PORT = '/dev/ttyACM0' 
BAUD_RATE = 9600
ser = None 

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
    print("--- Loading Context ---");
    if history_path is None: return None
    if os.path.exists(history_path):
        try:
            with open(history_path, "r") as f: print(f"--> Resuming from: '{history_path}'"); return json.load(f)
        except Exception as e: print(f"--> WARNING: Unreadable history: {e}"); return None
    else: print(f"--> New history at: '{history_path}'"); return None

def get_system_prompt(prompt_path):
    if prompt_path is None: print("--> Using empty prompt."); return [{"role": "system", "content": ""}]
    try:
        with open(prompt_path, "r", encoding="utf-8") as f: print(f"--> Loading prompt: '{prompt_path}'"); return [{"role": "system", "content": f.read()}]
    except FileNotFoundError: print(f"--> WARNING: Prompt not found. Using empty prompt."); return [{"role": "system", "content": ""}]
    except Exception as e: print(f"--> WARNING: Unreadable prompt: {e}. Using empty prompt."); return [{"role": "system", "content": ""}]

def save_history(messages, history_path):
    if history_path is None: return
    try:
        with open(history_path, "w") as f: json.dump(messages, f, indent=4)
    except Exception as e: print(f"Error saving history: {e}")

def main_loop(recognizer, microphone, args):
    """ The main application logic loop with data chunking. """
    global ser
    if USE_ARDUINO:
        try:
            print("--- Arduino Connection ---"); ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1); time.sleep(2) 
            print("Arduino connection successful."); print("--------------------------")
        except serial.SerialException as e: print(f"!!! ARDUINO FAILED TO CONNECT: {e}"); ser = None

    try:
        print("--- Loading Model ---");
        with SuppressStderr(): llm = Llama(model_path=model_path, n_ctx=32768, n_threads=8, n_gpu_layers=0, verbose=False)
        print("Model loaded successfully.")
    except Exception as e: print(f"Error loading model: {e}"); exit()

    messages = load_history(args.history)
    if messages is None: messages = get_system_prompt(args.prompt)
    
    generation_params = {"max_tokens": 2048, "stop": ["<|eot_id|>"], "stream": True, "mirostat_mode": 2, "mirostat_tau": 7.5, "mirostat_eta": 0.1, "repeat_penalty": 1.15, "presence_penalty": -0.1, "frequency_penalty": 0.1, "top_k": 50, "seed": -1}
    print("\n--- Chat with the AI (type 'news' or 'update' for headlines) ---")

    while True:
        user_input = None
        if recognizer and microphone:
            print("You (speak now, or press Enter to type): ", end="", flush=True)
            try:
                with microphone as source:
                    audio = recognizer.listen(source, timeout=4, phrase_time_limit=15)
                print("\r>>> Recognizing...                        ", end="", flush=True)
                user_input = recognizer.recognize_google(audio)
                print(f"\rYou: {user_input}                             ")
            except sr.WaitTimeoutError:
                print("\rYou (typing): ", end="", flush=True)
                user_input = input()
            except (sr.UnknownValueError, sr.RequestError):
                print("\r(Could not understand audio, please type instead)")
                user_input = input("You (typing): ")
        else:
            user_input = input("You: ")

        if not user_input: continue
        if user_input.lower() in ["quit", "exit"]: break

        if user_input.lower() in ["news", "update"]:
            news_string = get_latest_news()
            print(f"News: {news_string}")
            if ser:
                try:
                    message_to_send = f"GEMMA:{news_string}\n"
                    ser.write(message_to_send.encode('utf-8'))
                    ser.flush()
                except serial.SerialException as e: print(f"!!! (Error sending news: {e}) !!!")
            continue

        if ser:
            try:
                user_question_clean = user_input.strip().replace('\n', ' ');
                user_question_to_send = f"USER:{user_question_clean}\n"
                ser.write(user_question_to_send.encode('utf-8'))
                ser.flush()
            except serial.SerialException as e: print(f"!!! (Error sending user question: {e}) !!!")
        
        messages.append({"role": "user", "content": user_input})
        response_stream = llm.create_chat_completion(messages=messages, **generation_params)
        assistant_response_full = ""
        print("AI: ", end="", flush=True)

        for chunk in response_stream:
            delta = chunk['choices'][0]['delta']
            if "content" in delta:
                text_chunk = delta["content"]
                print(text_chunk, end="", flush=True)
                assistant_response_full += text_chunk
        print()

        messages.append({"role": "assistant", "content": assistant_response_full.strip()})
        
        # --- NEW CHUNKING LOGIC TO SEND DATA TO ARDUINO ---
        if ser:
            try:
                gemma_response_clean = assistant_response_full.strip().replace('\n', ' ')
                # Arduino buffer is 256, chunk size of 200 is very safe.
                CHUNK_SIZE = 200 

                if len(gemma_response_clean) <= CHUNK_SIZE:
                    # Message is short, send with the simple "GEMMA:" prefix
                    message_to_send = f"GEMMA:{gemma_response_clean}\n"
                    print(f"--- [DEBUG] Sending single packet ({len(message_to_send)} bytes)... ---")
                    ser.write(message_to_send.encode('utf-8'))
                    ser.flush()
                else:
                    # Message is long, send in chunks
                    print(f"--- [DEBUG] Sending long message in chunks... ---")
                    
                    # Send the first chunk with "GEMMA_START:"
                    first_chunk = gemma_response_clean[:CHUNK_SIZE]
                    message_to_send = f"GEMMA_START:{first_chunk}\n"
                    ser.write(message_to_send.encode('utf-8'))
                    ser.flush()
                    print(f"--- [DEBUG] Sent START chunk ({len(message_to_send)} bytes)... ---")
                    time.sleep(0.05) # Small delay for Arduino to process

                    # Send the rest of the chunks with "GEMMA_APPEND:"
                    for i in range(CHUNK_SIZE, len(gemma_response_clean), CHUNK_SIZE):
                        next_chunk = gemma_response_clean[i:i + CHUNK_SIZE]
                        message_to_send = f"GEMMA_APPEND:{next_chunk}\n"
                        ser.write(message_to_send.encode('utf-8'))
                        ser.flush()
                        print(f"--- [DEBUG] Sent APPEND chunk ({len(message_to_send)} bytes)... ---")
                        time.sleep(0.05) # Small delay for Arduino to process

            except serial.SerialException as e:
                print(f"!!! (Error sending AI response to Arduino: {e}) !!!")
        
        save_history(messages, args.history)

    if ser: ser.close(); print("--- Arduino connection closed. ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="An AI chat terminal with Arduino integration.")
    parser.add_argument('-p', '--prompt', type=str, help="Path to the system prompt text file.")
    parser.add_argument('-H', '--history', type=str, help="Path to conversation history JSON file.")
    args = parser.parse_args()

    recognizer = None
    microphone = None
    
    with SuppressALSAErrors():
        try:
            recognizer = sr.Recognizer(); microphone = sr.Microphone()
            with microphone as source:
                print("Please wait. Calibrating microphone..."); recognizer.adjust_for_ambient_noise(source, duration=1.5); print("Calibration complete.")
            main_loop(recognizer, microphone, args)
        except Exception as e: 
            print(f"!!! Mic error: {e}. Voice input will be disabled. Continuing in text-only mode.")
            main_loop(None, None, args)
        except KeyboardInterrupt:
            print("\n--- Exiting gracefully ---")
        finally:
            print("\nGoodbye!")