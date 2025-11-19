"""
Console Widget Component

Displays console output with auto-scrolling.
"""

import queue
from PyQt6.QtWidgets import QWidget, QTextEdit, QVBoxLayout, QGroupBox
from PyQt6.QtCore import QTimer

from .theme import VSCodeTheme


class ConsoleRedirector:
    """Redirects stdout/stderr to Qt signal for thread-safe GUI updates"""

    def __init__(self, message_queue, original_stream):
        self.message_queue = message_queue
        self.original_stream = original_stream

    def write(self, message):
        # Write to original console
        self.original_stream.write(message)
        self.original_stream.flush()

        # Queue message for GUI thread to process
        if self.message_queue:
            self.message_queue.put(message)

    def flush(self):
        self.original_stream.flush()


class ConsoleWidget(QWidget):
    """Console output widget with auto-scrolling"""

    def __init__(self):
        super().__init__()
        self.theme = VSCodeTheme
        self.console_queue = queue.Queue()

        self.setup_ui()
        self.setup_timer()

    def setup_ui(self):
        """Setup the UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # Group box
        group = QGroupBox("📜 Console Log")
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(12, 16, 12, 12)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setMinimumHeight(150)
        group_layout.addWidget(self.text_edit)

        group.setLayout(group_layout)
        layout.addWidget(group)
        self.setLayout(layout)

    def setup_timer(self):
        """Setup timer for processing console queue"""
        self.console_timer = QTimer()
        self.console_timer.timeout.connect(self.process_console_queue)
        self.console_timer.start(50)  # Process every 50ms

    def process_console_queue(self):
        """Process queued console messages"""
        try:
            while True:
                message = self.console_queue.get_nowait()
                self.text_edit.insertPlainText(message)
                self.text_edit.verticalScrollBar().setValue(
                    self.text_edit.verticalScrollBar().maximum()
                )
        except queue.Empty:
            pass

    def get_queue(self):
        """Get the message queue for console redirection"""
        return self.console_queue
