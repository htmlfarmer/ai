import os
import logging
from llama_cpp import Llama

# configure basic logging
logging.basicConfig(level=os.environ.get("AI_CORE_LOG_LEVEL", "INFO"))
logger = logging.getLogger("ai_core")

class SuppressStderr:
    """A context manager to suppress standard error messages, like those from ALSA."""
    def __enter__(self):
        # duplicate stderr fd so we can restore it later
        self._original_stderr_fd = os.dup(2)
        # open devnull and replace stderr with it
        self._devnull_fd = os.open(os.devnull, os.O_WRONLY)
        os.dup2(self._devnull_fd, 2)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # restore original stderr and close fds
        try:
            os.dup2(self._original_stderr_fd, 2)
        except OSError:
            pass
        try:
            os.close(self._original_stderr_fd)
        except OSError:
            pass
        try:
            os.close(self._devnull_fd)
        except OSError:
            pass
        return False

class AIModel:
    def __init__(self):
        """Initializes and loads the AI model with performance-oriented settings."""
        self.llm = None

        # allow overriding via environment variables
        default_model = "/home/asher/.lmstudio/models/lmstudio-community/gemma-3-1b-it-GGUF/gemma-3-1b-it-Q4_K_M.gguf"
        model_path = os.environ.get("AI_MODEL_PATH", default_model)
        n_threads = int(os.environ.get("AI_N_THREADS", max(1, (os.cpu_count() or 1))))
        n_gpu_layers = int(os.environ.get("AI_N_GPU_LAYERS", -1))

        self.config = {
            "model_path": model_path,
            "llama_params": {
                "n_ctx": int(os.environ.get("AI_N_CTX", 4096)),
                "n_threads": n_threads,
                "n_gpu_layers": n_gpu_layers,
                "verbose": False
            },
            "generation_params": {
                "temperature": float(os.environ.get("AI_TEMPERATURE", 1.0)),
                "top_k": int(os.environ.get("AI_TOP_K", 40)),
                "top_p": float(os.environ.get("AI_TOP_P", 0.95)),
                "repeat_penalty": float(os.environ.get("AI_REPEAT_PENALTY", 1.1)),
                "max_tokens": int(os.environ.get("AI_MAX_TOKENS", 1024)),
                "stop": ["<|eot_id|>"],
                "stream": True # CRITICAL for live "thinking" effect
            }
        }

        logger.info("AI Core: Preparing to load model from %s", model_path)
        if not os.path.isfile(model_path):
            logger.error("Model file not found at: %s", model_path)
            logger.error("Set AI_MODEL_PATH env or update self.config['model_path'] and retry.")
            return

        try:
            with SuppressStderr():
                self.llm = Llama(model_path=model_path, **self.config["llama_params"])
            logger.info("AI Core: Model loaded successfully.")
        except Exception as e:
            logger.exception("Fatal: Error loading model: %s", e)

    def ask(self, user_question, conversation_history=None, stop_event=None):
        """
        Generator: yields response chunks as they arrive.
        If stop_event is provided and becomes set, the generator attempts to stop early.
        """
        if not self.llm:
            yield "Error: The AI model is not loaded."
            return

        messages = [{"role": "system", "content": "You are a helpful and friendly assistant."}]
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_question})

        try:
            response_stream = self.llm.create_chat_completion(
                messages=messages,
                **self.config["generation_params"]
            )
            for chunk in response_stream:
                # allow external stop signal
                if stop_event and getattr(stop_event, "is_set", lambda: False)():
                    logger.debug("ask(): stop_event set, breaking stream.")
                    break
                choice = chunk.get('choices', [])[0] if chunk.get('choices') else {}
                delta = choice.get('delta', {})
                if "content" in delta:
                    yield delta["content"]  # Yield each piece of text
        except Exception as e:
            logger.exception("Error during AI generation: %s", e)
            yield "Sorry, an error occurred while generating the response."

# Optional quick self-test. Only runs when AI_CORE_SELF_TEST=1 to avoid accidental loads.
if __name__ == "__main__" and os.environ.get("AI_CORE_SELF_TEST") == "1":
    ai = AIModel()
    if ai.llm:
        logger.info("Model initialized. Sending test prompt...")
        for part in ai.ask("Say hello in one sentence."):
            print(part, end="", flush=True)
        print()
