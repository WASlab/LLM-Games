# player.py
from enum import Enum
from typing import Optional, Dict
from mafia.enums import Role, Faction

class Player:
    def __init__(self, name: str, role: Role):
        self.name: str = name
        self.role: Role = role
        self.faction: Faction = role.faction()
        self.alive: bool = True

        # Night action state
        self.target: Optional[str] = None
        self.is_roleblocked: bool = False

        # Day state
        self.vote: Optional[str] = None
        self.discussion_tokens: int = 0  # Optional, used if simulating timed discussion

        # Action tracking
        self.has_accused: bool = False
        self.predicted_roles: Dict[str, str] = {}  # name -> role prediction
        self.questions_asked: Dict[str, int] = {}  # name -> times asked
        self.whispers_sent: Dict[str, str] = {}     # name -> last whisper

    def reset_night_state(self):
        self.target = None
        self.is_roleblocked = False

    def reset_day_state(self):
        self.vote = None
        self.discussion_tokens = 0
        self.has_accused = False
        self.predicted_roles.clear()
        self.questions_asked.clear()
        self.whispers_sent.clear()

    def can_act(self) -> bool:
        return self.alive and not self.is_roleblocked

    def can_speak(self) -> bool:
        return self.alive and self.discussion_tokens > 0

    def accuse(self, target: str, game_state):
        if not self.alive or self.has_accused:
            return False
        game_state.log_hidden(self.name, f"Accused {target}")
        self.has_accused = True
        return True

    def predict_role(self, target: str, predicted_role: str, game_state):
        if not self.alive:
            return False
        self.predicted_roles[target] = predicted_role
        game_state.log_hidden(self.name, f"Predicted {target} as {predicted_role}")
        return True

    def question(self, target: str, question_text: str, game_state):
        if not self.alive or self.discussion_tokens <= 0:
            return False
        self.questions_asked[target] = self.questions_asked.get(target, 0) + 1
        self.discussion_tokens -= 1
        game_state.log_hidden(self.name, f"Asked {target}: {question_text}")
        return True

    def whisper(self, target: str, whisper_text: str, game_state):
        if not self.alive or not game_state.is_alive(target):
            return False
        self.whispers_sent[target] = whisper_text
        game_state.log_hidden(self.name, f"Whispered to {target}: {whisper_text}")
        return True

    def vote_for(self, target: str, game_state):
        if not self.alive:
            return False
        self.vote = target
        game_state.log_hidden(self.name, f"Voted for {target}")
        return True

    def log_hidden(self, game_state, message: str):
        game_state.hidden_log.append({
            "tick": game_state.current_tick,
            "agent": self.name,
            "msg": message
        })

    def __repr__(self):
        return f"<{self.name} - {self.role.name}{' (Dead)' if not self.alive else ''}>"
