# message_bus.py
from PyQt6.QtCore import QObject, pyqtSignal

class MessageBus(QObject):
    message = pyqtSignal(str)
    timedMessage = pyqtSignal(str, int)

bus = MessageBus()
