import gi
import json

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

HISTORY_FILE = 'conversation_history.json'

class ResponseWindow(Gtk.Window):
    def __init__(self, question, answer, app_controller, conversation_history=None):
        super().__init__(title="AI Assistant Response")
        self.question = question
        self.answer = answer
        self.app_controller = app_controller # To call back for follow-ups
        self.conversation_history = conversation_history if conversation_history else []

        # --- Window Setup ---
        self.set_default_size(600, 400)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(10)

        # --- Main Layout Box (Vertical) ---
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(vbox)

        # --- Display Original Question ---
        question_label = Gtk.Label(label=f"You asked: \"{self.question}\"", xalign=0)
        question_label.set_line_wrap(True)
        vbox.pack_start(question_label, False, False, 0)

        # --- Display AI Answer in a Scrollable Text View ---
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_hexpand(True)
        scrolled_window.set_vexpand(True)
        self.textview = Gtk.TextView()
        self.textview.set_editable(False)
        self.textview.set_cursor_visible(False)
        self.textview.set_wrap_mode(Gtk.WrapMode.WORD)
        self.textbuffer = self.textview.get_buffer()
        self.textbuffer.set_text(self.answer)
        scrolled_window.add(self.textview)
        vbox.pack_start(scrolled_window, True, True, 0)

        # --- Follow-up Question Area ---
        hbox_followup = Gtk.Box(spacing=6)
        followup_entry = Gtk.Entry()
        followup_entry.set_placeholder_text("Ask a follow-up question...")
        # Connect 'Enter' key press to the send button's action
        followup_entry.connect("activate", self.on_follow_up_clicked, followup_entry)
        hbox_followup.pack_start(followup_entry, True, True, 0)
        
        send_button = Gtk.Button(label="Send")
        send_button.connect("clicked", self.on_follow_up_clicked, followup_entry)
        hbox_followup.pack_start(send_button, False, False, 0)
        vbox.pack_start(hbox_followup, False, True, 0)

        # --- Action Buttons (Save, Close) ---
        action_bar = Gtk.ActionBar()
        close_button = Gtk.Button(label="Close")
        close_button.connect("clicked", lambda w: self.destroy())
        action_bar.pack_end(close_button)
        
        save_button = Gtk.Button(label="Save Conversation")
        save_button.connect("clicked", self.on_save_clicked)
        action_bar.pack_start(save_button)
        vbox.pack_start(action_bar, False, True, 0)
        
        # Save this conversation automatically to history
        self.add_to_history()

    def on_save_clicked(self, widget):
        # This function could be expanded to save to a custom text file
        # For now, it just confirms it's saved in the main history file.
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="Conversation Saved",
        )
        dialog.format_secondary_text(f"This exchange has been saved to {HISTORY_FILE}.")
        dialog.run()
        dialog.destroy()
        
    def add_to_history(self):
        try:
            with open(HISTORY_FILE, 'r+') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = []
        
        # Add the new exchange
        data.append({"question": self.question, "answer": self.answer})
        
        # Write back to the file
        with open(HISTORY_FILE, 'w') as f:
            json.dump(data, f, indent=4)

    def on_follow_up_clicked(self, widget, entry):
        follow_up_question = entry.get_text()
        if follow_up_question:
            # Update the conversation history for context
            current_conversation = self.conversation_history
            current_conversation.append({"role": "user", "content": self.question})
            current_conversation.append({"role": "assistant", "content": self.answer})
            
            # Tell the main applet to handle the new question
            self.app_controller.handle_new_question(follow_up_question, current_conversation)
            
            # Close the current window
            self.destroy()