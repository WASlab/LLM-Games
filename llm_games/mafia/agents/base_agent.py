# === mafia/agents/base_agent.py ===

from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseAgent(ABC):
    """
    Base abstract agent class for Mafia.
    Each agent must at least implement:
      - observe(observation): to receive environment state
      - act(): to return an action dictionary
      - reset(): optional, if the agent needs to reset between games
    """
    def __init__(self, name: str):
        self.name = name  # The agent’s name (should match player.name, but not strictly required)

    @abstractmethod
    def observe(self, observation: Dict[str, Any]):
        """
        Called by the environment or simulation to present the agent with
        the current game observation (public messages, roles, day/phase info, etc.).
        The agent should store it internally for decision making.
        """
        pass

    @abstractmethod
    def act(self) -> Dict[str, Any]:
        """
        Called after the agent has observed the environment state and must
        produce an action dictionary, e.g. {"action": "accuse", "target": "Alice"}.
        """
        pass

    def reset(self):
        """
        Optional: Clear internal memory or states if needed between episodes/games.
        """
        pass
