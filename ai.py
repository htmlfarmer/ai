# FILENAME: ai.py (Robust, General Scraper Version)

import json
import os
import sys
import serial
import time
import argparse
from llama_cpp import Llama
import requests
from bs4 import BeautifulSoup

# --- SETTINGS & All other setup code is UNCHANGED ---
USE_ARDUINO = True
model_path = "/home/asher/.lmstudio/models/lmstudio-community/gemma-3-1b-it-GGUF/gemma-3-1b-it-Q4_K_M.gguf"
SERIAL_PORT = '/dev/ttyACM0' 
BAUD_RATE = 9600
ser = None 

class SuppressStderr:
    def __enter__(self): self.original_stderr = sys.stderr; self.devnull = open(os.devnull, 'w'); sys.stderr = self.devnull
    def __exit__(self, exc_type, exc_val, exc_tb): sys.stderr = self.original_stderr; self.devnull.close()

# --- THIS IS THE CORRECTED SCRAPER FUNCTION ---
def get_latest_news():
    """
    Scrapes the Wikipedia Current Events portal's main content area.
    This is a general approach that is more reliable than targeting specific sections.
    """
    url = "https://en.wikipedia.org/wiki/Portal:Current_events"
    headlines = []
    
    try:
        print("--> Fetching latest news from Wikipedia...")
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # --- THE NEW, ROBUST SELECTOR ---
        # Find the main content div, then get all list items inside it.
        # This is much less likely to break than targeting a specific, changing ID.
        news_items = soup.select('div#bodyContent li')
        
        if not news_items:
            return "Could not find any list items in the main content of the page."

        for item in news_items:
            # Clean up the text
            text = item.get_text(strip=True).replace('(pictured)', '').replace('[edit]', '')
            # Ignore very short or junk list items
            if len(text) > 20: # Increased length check to filter out more junk
                headlines.append(text)
            
        if headlines:
            # We'll limit the output to the first 7 clean headlines to keep it manageable
            return " | ".join(headlines[:7])
        else:
            return "Could not find any valid news headlines in the main content."

    except requests.exceptions.RequestException as e:
        print(f"!!! Error fetching the webpage: {e}")
        return "Error: Could not connect to the internet."
    except Exception as e:
        print(f"!!! An error occurred during scraping: {e}")
        return "Error: Could not parse the news page."


# --- All other helper functions and the main() loop are UNCHANGED ---
def load_history(history_path):
    print("--- Loading Context ---")
    if history_path is None: return None
    if os.path.exists(history_path):
        try:
            with open(history_path, "r") as f: print(f"--> Resuming from: '{history_path}'"); return json.load(f)
        except Exception as e: print(f"--> WARNING: Unreadable history: {e}"); return None
    else: print(f"--> New history will be created at: '{history_path}'"); return None
def get_system_prompt(prompt_path):
    if prompt_path is None: print("--> Using empty system prompt."); return [{"role": "system", "content": ""}]
    try:
        with open(prompt_path, "r", encoding="utf-8") as f: print(f"--> Loading prompt: '{prompt_path}'"); return [{"role": "system", "content": f.read()}]
    except FileNotFoundError: print(f"--> WARNING: Prompt not found. Using empty prompt."); return [{"role": "system", "content": ""}]
    except Exception as e: print(f"--> WARNING: Unreadable prompt: {e}. Using empty prompt."); return [{"role": "system", "content": ""}]
def save_history(messages, history_path):
    if history_path is None: return
    try:
        with open(history_path, "w") as f: json.dump(messages, f, indent=4)
    except Exception as e: print(f"Error saving history: {e}")


def main():
    parser = argparse.ArgumentParser(description="An AI chat terminal with Arduino integration.")
    parser.add_argument('-p', '--prompt', type=str, help="Path to the system prompt text file.")
    parser.add_argument('-H', '--history', type=str, help="Path to conversation history JSON file.")
    args = parser.parse_args()

    global ser
    
    if USE_ARDUINO:
        try:
            print("--- Arduino Connection ---"); print(f"Attempting to connect on port: {SERIAL_PORT}")
            ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            time.sleep(2) 
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
        user_input = input("You: ")
        if user_input.lower() in ["quit", "exit"]: break

        if user_input.lower() in ["news", "update"]:
            news_string = get_latest_news()
            print(f"News: {news_string}")
            if ser:
                try:
                    message_to_send = f"GEMMA:{news_string}\n"
                    print(f"--- [Sending News to Arduino: {len(message_to_send)} bytes] ---")
                    ser.write(message_to_send.encode('utf-8'))
                except serial.SerialException as e:
                    print(f"--- (Error sending news to Arduino: {e}) ---")
            continue

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