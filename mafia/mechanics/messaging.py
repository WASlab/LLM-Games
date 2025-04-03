# mafia/mechanics/messaging.py
from typing import Dict, List, Optional, Tuple
from mafia.enums import Phase

class Message:
    def __init__(self, sender: str, content: str, target: Optional[str] = None, private: bool = False):
        self.sender = sender              # Who sent the message
        self.content = content            # What was said (raw text or structured)
        self.target = target              # If whispering or targeting another player
        self.private = private            # Whisper if True, public otherwise

    def render(self) -> str:
        if self.private:
            return f"[WHISPER] {self.sender} → {self.target}: {self.content}"
        elif self.target:
            return f"{self.sender} → {self.target}: {self.content}"
        return f"{self.sender}: {self.content}"


class MessagingSystem:
    def __init__(self):
        self.history: List[Message] = []

    def send_public(self, sender: str, content: str):
        msg = Message(sender=sender, content=content)
        self.history.append(msg)
        return msg

    def send_private(self, sender: str, recipient: str, content: str):
        msg = Message(sender=sender, content=content, target=recipient, private=True)
        self.history.append(msg)
        return msg

    def get_visible_messages(self, player_name: str, phase: Phase) -> List[str]:
        visible = []
        for msg in self.history:
            if not msg.private:
                visible.append(msg.render())
            elif msg.private and (msg.sender == player_name or msg.target == player_name):
                visible.append(msg.render())
        return visible

    def get_all_messages(self) -> List[str]:
        return [msg.render() for msg in self.history]

    def clear(self):
        self.history.clear()

    def get_log_data(self) -> List[Dict]:
        return [{
            "sender": msg.sender,
            "target": msg.target,
            "private": msg.private,
            "content": msg.content
        } for msg in self.history]
