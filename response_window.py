import gi
import os
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Pango

class ResponseWindow(Gtk.Window):
    """The main chat window UI for the AI Assistant."""
    def __init__(self, app_controller):
        super().__init__(title="AI Assistant")
        self.app_controller = app_controller
        self.conversation_history = []
        self.set_default_size(700, 600)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(10)

        # Get font size from env var, default to 12pt
        self.font_size_pt = int(os.environ.get("AI_FONT_SIZE", 12))

        # Create text tags for styling the chat log
        self.textbuffer = Gtk.TextBuffer()
        self.textbuffer.create_tag("user_question", weight=Pango.Weight.BOLD, foreground="#3465a4", size=self.font_size_pt * 1024)
        self.textbuffer.create_tag("ai_response", foreground="#4e9a06", size=self.font_size_pt * 1024)
        self.textbuffer.create_tag("info_text", foreground="#888a85", style=Pango.Style.ITALIC, size=self.font_size_pt * 1024)
        self.textbuffer.create_tag("error_text", foreground="#cc0000", style=Pango.Style.ITALIC, size=self.font_size_pt * 1024)

        # --- UI Layout ---
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(vbox)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_hexpand(True); scrolled_window.set_vexpand(True)
        self.textview = Gtk.TextView(buffer=self.textbuffer)
        self.textview.set_editable(False)
        self.textview.set_wrap_mode(Gtk.WrapMode.WORD)
        scrolled_window.add(self.textview)
        vbox.pack_start(scrolled_window, True, True, 0)

        hbox_input = Gtk.Box(spacing=6)
        self.input_entry = Gtk.Entry(placeholder_text="Ask a question...")
        self.input_entry.connect("activate", self.on_send_clicked)
        hbox_input.pack_start(self.input_entry, True, True, 0)
        
        # Use a Gtk.Stack to easily switch between Send and Stop buttons
        self.button_stack = Gtk.Stack()
        self.button_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        
        self.send_button = Gtk.Button(label="Send")
        self.send_button.connect("clicked", self.on_send_clicked)
        self.button_stack.add_named(self.send_button, "send")

        self.stop_button = Gtk.Button(label="Stop")
        self.stop_button.connect("clicked", self.on_stop_clicked)
        self.button_stack.add_named(self.stop_button, "stop")

        hbox_input.pack_start(self.button_stack, False, False, 0)
        vbox.pack_start(hbox_input, False, True, 0)

        self.status_bar = Gtk.Box(spacing=15)
        self.mem_label = Gtk.Label(label="Mem: ...")
        self.cpu_label = Gtk.Label(label="CPU: ...")
        self.status_bar.pack_start(self.mem_label, False, False, 0)
        self.status_bar.pack_start(self.cpu_label, False, False, 0)
        vbox.pack_start(self.status_bar, False, True, 0)

        self.append_to_log("Welcome to your AI Assistant! Ask a question to get started.", "info_text")

    def append_to_log(self, text, tag_name):
        end_iter = self.textbuffer.get_end_iter()
        self.textbuffer.insert_with_tags_by_name(end_iter, text, tag_name)
        self.textview.scroll_to_iter(self.textbuffer.get_end_iter(), 0.0, True, 0.0, 1.0)

    def on_send_clicked(self, widget):
        question = self.input_entry.get_text()
        if not question: return
        self.append_to_log(f"\n\nUser: {question}", "user_question")
        self.input_entry.set_text("")
        self.toggle_inputs(False)
        self.app_controller.handle_question_stream(question, self.conversation_history, self)

    def on_stop_clicked(self, widget):
        self.app_controller.stop_generation()

    def update_stats(self, mem_mb, cpu_percent):
        self.mem_label.set_text(f"Mem: {mem_mb:.1f} MB")
        self.cpu_label.set_text(f"CPU: {cpu_percent:.1f}%")

    def toggle_inputs(self, is_enabled):
        self.input_entry.set_sensitive(is_enabled)
        if is_enabled:
            self.button_stack.set_visible_child_name("send")
        else:
            self.button_stack.set_visible_child_name("stop")
            
    def add_response_to_history(self, question, answer):
        self.conversation_history.append({"role": "user", "content": question})
        self.conversation_history.append({"role": "assistant", "content": answer})
