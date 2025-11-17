import gi
import os
import threading
import time
import psutil
import signal
import logging

gi.require_version('Gtk', '3.0')
gi.require_version('AyatanaAppIndicator3', '0.1')
from gi.repository import Gtk, GObject, AyatanaAppIndicator3

from ai_core import AIModel
from response_window import ResponseWindow

APPINDICATOR_ID = 'ai-toolbar-applet'

# basic logging
logging.basicConfig(level=os.environ.get("AI_TOOLBAR_LOG_LEVEL", "INFO"))
logger = logging.getLogger("toolbar_applet")

class IndicatorApplet:
    """The main application controller."""
    def __init__(self):
        self.ai_model = AIModel()
        self.main_window = None
        self.process = psutil.Process(os.getpid())
        
        self.is_generating = False
        self.stop_generation_event = None

        self.indicator = AyatanaAppIndicator3.Indicator.new(
            APPINDICATOR_ID, 'system-search', AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )

        # set icon based on model availability
        if not getattr(self.ai_model, "llm", None):
            # model failed to load; use an error icon
            try:
                self.indicator.set_icon_full("dialog-error", "Model missing")
            except Exception:
                pass
        else:
            try:
                self.indicator.set_icon_full("system-search", "Assistant")
            except Exception:
                pass

        self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_menu(self.build_menu())

        # setup signal handlers for graceful termination
        signal.signal(signal.SIGINT, lambda *_: GObject.idle_add(self.on_quit, None))
        signal.signal(signal.SIGTERM, lambda *_: GObject.idle_add(self.on_quit, None))

        self.stop_monitor = threading.Event()
        self.monitor_thread = threading.Thread(target=self.system_monitor_loop, name="system-monitor")
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

    def build_menu(self):
        menu = Gtk.Menu()
        # keep a reference so we can enable/disable later
        self.menu_item_toggle = Gtk.MenuItem(label='Show/Hide Assistant')
        self.menu_item_toggle.connect('activate', self.on_toggle_window)
        # disable toggle if model not available
        if not getattr(self.ai_model, "llm", None):
            self.menu_item_toggle.set_sensitive(False)
        menu.append(self.menu_item_toggle)

        item_quit = Gtk.MenuItem(label='Quit')
        item_quit.connect('activate', self.on_quit)
        menu.append(item_quit)
        menu.show_all()
        return menu

    def on_toggle_window(self, _):
        if self.main_window is None:
            self.main_window = ResponseWindow(self)
            self.main_window.connect("destroy", self.on_window_closed)
            self.main_window.show_all()
        self.main_window.present()

    def handle_question_stream(self, question, history, window):
        # don't start another generation if one is running
        if self.is_generating:
            return

        # ensure model is loaded before starting
        if not getattr(self.ai_model, "llm", None):
            GObject.idle_add(window.append_to_log, "Error: AI model is not loaded. Check model path or logs.", "error_text")
            return

        self.is_generating = True
        self.stop_generation_event = threading.Event()
        # disable inputs on the UI while generation happens
        GObject.idle_add(window.toggle_inputs, False)
        try:
            thread = threading.Thread(target=self.do_ai_stream, args=(question, history, window, self.stop_generation_event))
            thread.daemon = True
            thread.start()
        except Exception as e:
            self.is_generating = False
            GObject.idle_add(window.append_to_log, f"Error starting generation thread: {e}", "error_text")

    def stop_generation(self):
        if self.stop_generation_event:
            self.stop_generation_event.set()

    def do_ai_stream(self, question, history, window, stop_event):
        GObject.idle_add(window.append_to_log, "\n\nAI: ", "ai_response")
        full_response, was_stopped = "", False

        for chunk in self.ai_model.ask(question, conversation_history=history):
            if stop_event.is_set():
                was_stopped = True
                break
            full_response += chunk
            GObject.idle_add(window.append_to_log, chunk, "ai_response")
            
        if was_stopped:
            GObject.idle_add(window.append_to_log, "\n[Stopped by user]", "error_text")

        # peak memory not tracked anymore; call on_stream_done without a peak value
        GObject.idle_add(self.on_stream_done, window, question, full_response)

    def on_stream_done(self, window, question, full_response, peak_mem_mb=None):
        self.is_generating = False
        window.add_response_to_history(question, full_response)
        window.toggle_inputs(True)
        mem_mb = self.process.memory_info().rss / (1024 * 1024)
        cpu = psutil.cpu_percent(interval=None)
        # no peak value displayed any more
        window.update_stats(mem_mb, cpu)
        return False

    def system_monitor_loop(self):
        while not self.stop_monitor.is_set():
            if self.main_window:
                try:
                    mem_mb = self.process.memory_info().rss / (1024 * 1024)
                    cpu = psutil.cpu_percent(interval=None)
                    # guard in case the window was destroyed just before updating
                    GObject.idle_add(self.main_window.update_stats, mem_mb, cpu)
                except Exception:
                    # swallow transient errors - monitor should not kill app
                    pass
            time.sleep(2)

    def on_window_closed(self, window, event=None):
        if self.main_window:
            # hide and clear reference so monitor knows it's gone
            try:
                self.main_window.hide()
            except Exception:
                pass
            self.main_window = None
        return False

    def on_quit(self, _):
        logger.info("Shutting down applet...")
        # signal monitor and any ongoing generation to stop
        self.stop_monitor.set()
        if self.stop_generation_event:
            try:
                self.stop_generation_event.set()
            except Exception:
                pass

        # attempt to join monitor thread (short timeout)
        try:
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=1.0)
        except Exception:
            pass

        try:
            self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.PASSIVE)
        except Exception:
            pass
        Gtk.main_quit()

if __name__ == "__main__":
    applet = IndicatorApplet()
    print("AI Toolbar Applet is running.")
    Gtk.main()
