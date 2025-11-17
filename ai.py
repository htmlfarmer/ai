import os
import sys
import argparse
from llama_cpp import Llama
from flask import Flask, request, render_template_string

# Suppress llama_cpp's initial output for a cleaner experience
class SuppressStderr:
    def __enter__(self):
        self.original_stderr = os.dup(2)
        self.devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(self.devnull, 2)
    def __exit__(self, exc_type, exc_val, exc_tb):
        os.dup2(self.original_stderr, 2)
        os.close(self.devnull)

class AIModel:
    def __init__(self):
        """
        Initializes the AI model by loading it into memory.
        """
        self.llm = None
        self.system_prompt_path = "/home/asher/private/O3.txt"
        self.default_system_prompt = "You are a helpful assistant. Keep your answers concise."
        self.max_system_prompt_chars = 8000 # A safe character limit to avoid context overflow
        self.system_prompt_name = None

        try:
            if os.path.exists(self.system_prompt_path):
                with open(self.system_prompt_path, 'r') as f:
                    prompt_content = f.read().strip()
                    if len(prompt_content) > self.max_system_prompt_chars:
                        print(f"!!! WARNING: System prompt from {self.system_prompt_path} was too long and has been truncated to {self.max_system_prompt_chars} characters.")
                        self.default_system_prompt = prompt_content[:self.max_system_prompt_chars]
                    else:
                        self.default_system_prompt = prompt_content
                self.system_prompt_name = "O3"
                print(f"--> AI Core: Loaded system prompt from {self.system_prompt_path}")
        except Exception as e:
            print(f"!!! WARNING: Could not load system prompt file: {e}")

        self.config = {
            "model_path": "/home/asher/.lmstudio/models/lmstudio-community/gemma-3-1b-it-GGUF/gemma-3-1b-it-Q4_K_M.gguf",
            "llama_params": {
                "n_ctx": 4096, # Reduced context for quicker, single-shot questions
                "n_threads": 8,
                "n_gpu_layers": 0,
                "verbose": False
            },
            "generation_params": {
                "temperature": 2.0,
                "top_k": 40,
                "top_p": 0.95,
                "repeat_penalty": 1.1,
                "max_tokens": 1024, # Limit response length for notifications
                "stop": ["<|eot_id|>"],
                "mirostat_mode": 0,
                "mirostat_tau": 5.0,
                "mirostat_eta": 0.1,
            }
        }
        print("--> AI Core: Loading model...")
        try:
            with SuppressStderr():
                self.llm = Llama(model_path=self.config["model_path"], **self.config["llama_params"])
            print("--> AI Core: Model loaded successfully.")
        except Exception as e:
            print(f"!!! FATAL: Error loading model: {e}")
            # We can also use notify-send here to alert the user of a failure
            os.system(f'notify-send "AI Model Error" "Could not load the language model. Check terminal." -i error')


    def ask(self, user_question, additional_system_prompt, generation_params):
        """
        Takes a user's question and params, gets a response from the model, and returns it as a stream generator.
        """
        if not self.llm:
            yield "Error: The AI model is not loaded."
            return

        final_system_prompt = self.default_system_prompt
        if additional_system_prompt:
            final_system_prompt += "\n\n" + additional_system_prompt

        # Truncate system_prompt if it's too long to prevent crashes
        if len(final_system_prompt) > self.max_system_prompt_chars:
            final_system_prompt = final_system_prompt[:self.max_system_prompt_chars]
            print(f"!!! WARNING: System prompt was too long and was truncated to {self.max_system_prompt_chars} characters.")

        messages = [
            {"role": "system", "content": final_system_prompt},
            {"role": "user", "content": user_question}
        ]

        # Combine default params with incoming ones, letting incoming ones overwrite
        final_gen_params = self.config["generation_params"].copy()
        
        # Type conversion and filtering for incoming params
        for key, value in generation_params.items():
            if value is not None and value != '':
                try:
                    if key in ['temperature', 'top_p', 'repeat_penalty', 'mirostat_tau', 'mirostat_eta']:
                        final_gen_params[key] = float(value)
                    elif key in ['top_k', 'max_tokens', 'mirostat_mode']:
                        final_gen_params[key] = int(value)
                except (ValueError, TypeError):
                    pass # Keep default if conversion fails

        try:
            response_stream = self.llm.create_chat_completion(
                messages=messages,
                stream=True,
                **final_gen_params
            )
            for chunk in response_stream:
                content = chunk['choices'][0]['delta'].get('content')
                if content:
                    yield content
        except Exception as e:
            print(f"Error during AI generation: {e}")
            yield "Sorry, an error occurred while generating the response."

# --- Web Interface (using Flask) ---

# Check if model loaded successfully before starting the web server
ai_model = AIModel()
if not ai_model.llm:
    print("!!! FATAL: AI Model not loaded. Web server will not start.")
    exit()

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chat with AI</title>
    <style>
        body { font-family: sans-serif; max-width: 800px; margin: auto; padding: 20px; background-color: #f4f4f4; color: #333; }
        h1, h2 { color: #333; }
        #qa-form { display: flex; flex-direction: column; margin-bottom: 20px; }
        #question-container { display: flex; }
        #question { flex-grow: 1; padding: 10px; border: 1px solid #ccc; border-radius: 4px; }
        button { padding: 10px 15px; border: none; background-color: #007bff; color: white; border-radius: 4px; cursor: pointer; margin-left: 10px; }
        button:hover { background-color: #0056b3; }
        button:disabled { background-color: #cccccc; }
        #response-container { background-color: white; padding: 15px; border-radius: 4px; border: 1px solid #ddd; min-height: 50px; }
        #response { white-space: pre-wrap; }
        details { margin-top: 15px; border: 1px solid #ccc; border-radius: 4px; padding: 10px; }
        summary { cursor: pointer; font-weight: bold; }
        .param-grid { display: grid; grid-template-columns: 150px 1fr; gap: 10px; align-items: center; margin-top: 10px;}
        .param-grid label { font-weight: bold; }
        .param-grid input, .param-grid textarea, .param-grid select { width: 100%; box-sizing: border-box; padding: 5px; border-radius: 4px; border: 1px solid #ccc;}
        .param-grid textarea { resize: vertical; min-height: 60px; }
        .slider-container { display: flex; align-items: center; gap: 10px; }
        .slider-container input { flex-grow: 1; }
        .slider-container span { min-width: 35px; text-align: right; }
        .prompt-notice { font-style: italic; color: #555; margin-bottom: 5px; }
    </style>
</head>
<body>
    <h1>Ask your local AI model a question?</h1>
    <form id="qa-form">
        <div id="question-container">
            <input type="text" id="question" name="question" placeholder="Type your question here..." required autocomplete="off">
            <button type="submit">Ask</button>
        </div>
        <details>
            <summary>Advanced Options</summary>
            <div class="param-grid">
                <label for="system_prompt">System Prompt:</label>
                <div>
                    {% if system_prompt_name %}
                    <p class="prompt-notice">Private prompt '{{ system_prompt_name }}' is loaded. You can add more instructions below.</p>
                    {% endif %}
                    <textarea id="system_prompt" placeholder="Add additional system instructions here..."></textarea>
                </div>
                
                <label for="temperature">Temperature:</label>
                <div class="slider-container">
                    <input type="range" id="temperature" min="0" max="2" step="0.05" value="2.0">
                    <span id="temperature-value">2.0</span>
                </div>

                <label for="max_tokens">Max Tokens:</label>
                <input type="number" id="max_tokens" value="1024" min="1">
                
                <label for="top_k">Top K:</label>
                <input type="number" id="top_k" value="40" min="0">

                <label for="top_p">Top P:</label>
                 <div class="slider-container">
                    <input type="range" id="top_p" min="0" max="1" step="0.05" value="0.95">
                    <span id="top_p-value">0.95</span>
                </div>

                <label for="repeat_penalty">Repeat Penalty:</label>
                <div class="slider-container">
                    <input type="range" id="repeat_penalty" min="1" max="2" step="0.05" value="1.1">
                    <span id="repeat_penalty-value">1.1</span>
                </div>

                <label for="mirostat_mode">Mirostat Mode:</label>
                <select id="mirostat_mode">
                    <option value="0" selected>Disabled</option>
                    <option value="1">Mirostat v1</option>
                    <option value="2">Mirostat v2</option>
                </select>

                <label for="mirostat_tau">Mirostat Tau:</label>
                <div class="slider-container">
                    <input type="range" id="mirostat_tau" min="0" max="10" step="0.1" value="5.0">
                    <span id="mirostat_tau-value">5.0</span>
                </div>

                <label for="mirostat_eta">Mirostat Eta:</label>
                <div class="slider-container">
                    <input type="range" id="mirostat_eta" min="0" max="1" step="0.01" value="0.1">
                    <span id="mirostat_eta-value">0.1</span>
                </div>
            </div>
        </details>
    </form>
    <h2>Answer:</h2>
    <div id="response-container">
        <p id="response">The answer will appear here.</p>
    </div>

    <script>
        // Set initial system prompt safely, handling newlines and special characters
        // const initialSystemPrompt = {{ system_prompt|tojson }};
        // document.getElementById('system_prompt').value = initialSystemPrompt;

        function setupSlider(sliderId, displayId) {
            const slider = document.getElementById(sliderId);
            const display = document.getElementById(displayId);
            slider.addEventListener('input', () => display.textContent = slider.value);
        }

        setupSlider('temperature', 'temperature-value');
        setupSlider('top_p', 'top_p-value');
        setupSlider('repeat_penalty', 'repeat_penalty-value');
        setupSlider('mirostat_tau', 'mirostat_tau-value');
        setupSlider('mirostat_eta', 'mirostat_eta-value');

        document.getElementById('qa-form').addEventListener('submit', async function(e) {
            e.preventDefault();
            const questionInput = document.getElementById('question');
            const responseP = document.getElementById('response');
            const submitButton = document.querySelector('#qa-form button');

            const payload = {
                question: document.getElementById('question').value,
                system_prompt: document.getElementById('system_prompt').value,
                temperature: document.getElementById('temperature').value,
                max_tokens: document.getElementById('max_tokens').value,
                top_k: document.getElementById('top_k').value,
                top_p: document.getElementById('top_p').value,
                repeat_penalty: document.getElementById('repeat_penalty').value,
                mirostat_mode: document.getElementById('mirostat_mode').value,
                mirostat_tau: document.getElementById('mirostat_tau').value,
                mirostat_eta: document.getElementById('mirostat_eta').value,
            };

            responseP.textContent = 'Thinking...';
            submitButton.disabled = true;

            try {
                const response = await fetch('/ask', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let isFirstChunk = true;

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    if (isFirstChunk) {
                        responseP.textContent = '';
                        isFirstChunk = false;
                    }
                    responseP.textContent += decoder.decode(value, { stream: true });
                }

            } catch (error) {
                console.error('Fetch error:', error);
                responseP.textContent = 'An error occurred while fetching the response: ' + error.message;
            } finally {
                submitButton.disabled = false;
                questionInput.value = '';
            }
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, system_prompt_name=ai_model.system_prompt_name)

@app.route('/ask', methods=['POST'])
def ask_route():
    data = request.get_json()
    if not data or not data.get('question'):
        return "Error: No question provided", 400

    user_question = data['question']
    additional_system_prompt = data.get('system_prompt', '')
    
    generation_params = {
        'temperature': data.get('temperature'),
        'top_k': data.get('top_k'),
        'top_p': data.get('top_p'),
        'repeat_penalty': data.get('repeat_penalty'),
        'max_tokens': data.get('max_tokens'),
        'mirostat_mode': data.get('mirostat_mode'),
        'mirostat_tau': data.get('mirostat_tau'),
        'mirostat_eta': data.get('mirostat_eta'),
    }

    def generate():
        for chunk in ai_model.ask(user_question, additional_system_prompt, generation_params):
            yield chunk

    return app.response_class(generate(), mimetype='text/plain')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Run AI model as a web server or a single-shot command.")
    parser.add_argument('--cli', action='store_true', help='Run in command-line mode for use with scripts (e.g., PHP).')
    parser.add_argument('-q', '--question', type=str, help='Question to ask the model in CLI mode.')
    parser.add_argument('-s', '--system_prompt', type=str, default=None, help='Additional system prompt to append to the default one in CLI mode.')
    
    # Add other generation params for CLI
    parser.add_argument('-t', '--temperature', type=float, default=None)
    parser.add_argument('--top_k', type=int, default=None)
    parser.add_argument('--top_p', type=float, default=None)
    parser.add_argument('--repeat_penalty', type=float, default=None)
    parser.add_argument('--max_tokens', type=int, default=None)
    parser.add_argument('--mirostat_mode', type=int, default=None)
    parser.add_argument('--mirostat_tau', type=float, default=None)
    parser.add_argument('--mirostat_eta', type=float, default=None)

    args = parser.parse_args()

    # If --question is passed, run in CLI mode
    if args.question:
        additional_system_prompt = args.system_prompt
        
        generation_params = {
            k: v for k, v in vars(args).items() if v is not None and k not in ['cli', 'question', 'system_prompt']
        }

        for chunk in ai_model.ask(args.question, additional_system_prompt, generation_params):
            print(chunk, end='', flush=True)
        print() # Final newline
    else:
        print("--> Web Server: Starting Flask server...")
        print("--> Web Server: Access the web UI at http://127.0.0.1:5000")
        app.run(host='0.0.0.0', port=5000)
