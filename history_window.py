import gi
import json

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

HISTORY_FILE = 'conversation_history.json'

class HistoryWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Conversation History")
        self.set_default_size(500, 600)
        self.set_position(Gtk.WindowPosition.CENTER)

        scrolled_window = Gtk.ScrolledWindow()
        self.add(scrolled_window)

        textview = Gtk.TextView()
        textview.set_editable(False)
        textview.set_wrap_mode(Gtk.WrapMode.WORD)
        textbuffer = textview.get_buffer()
        scrolled_window.add(textview)

        try:
            with open(HISTORY_FILE, 'r') as f:
                history = json.load(f)
            
            formatted_history = ""
            for i, entry in enumerate(reversed(history)): # Show newest first
                formatted_history += f"--- Entry {len(history) - i} ---\n"
                formatted_history += f"Q: {entry['question']}\n"
                formatted_history += f"A: {entry['answer']}\n\n"
            
            textbuffer.set_text(formatted_history)

        except (FileNotFoundError, json.JSONDecodeError):
            textbuffer.set_text("No conversation history found.")

        self.show_all()
