# mafia/agents/base.py
from abc import ABC, abstractmethod

class BaseAgent(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def act(self, observation: dict) -> dict:
        """
        Returns an action dict like {"action": "accuse", "target": "Player3"}
        """
        pass
