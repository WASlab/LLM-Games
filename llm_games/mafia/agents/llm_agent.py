# === mafia/agents/llm_agent.py ===

import json
from typing import Dict, Any, Optional
from llm_games.mafia.agents.base_agent import BaseAgent

class LLMAgent(BaseAgent):
    """
    A base LLM-powered agent that can interact with the environment
    using local or API-based model backends.
    """
    def __init__(self,
                 name: str,
                 model_backend: callable,
                 tokenizer: Optional[callable] = None,
                 config: Optional[Dict[str, Any]] = None):
        """
        :param name: Agent/player name
        :param model_backend: A callable that takes a string prompt and returns a string
        :param tokenizer: Optional tokenizer if needed (e.g. for measuring token usage)
        :param config: Additional config for prompts, temperature, etc.
        """
        super().__init__(name)
        self.model_backend = model_backend
        self.tokenizer = tokenizer
        self.config = config or {}
        self.last_observation: Optional[Dict[str, Any]] = None

    def observe(self, observation: Dict[str, Any]):
        self.last_observation = observation

    def act(self) -> Dict[str, Any]:
        if not self.last_observation:
            return {"action": "pass"}

        prompt = self.build_prompt(self.last_observation)
        raw_output = self.model_backend(prompt)
        action = self.parse_action(raw_output)
        return action

    def build_prompt(self, obs: Dict[str, Any]) -> str:
        """
        Convert the environment observation into a textual prompt for the LLM.
        This method can be customized or replaced with chain-of-thought or JSON-based instructions.
        """
        # A simple example: show the day/phase, who’s alive, last messages, etc.
        # Then instruct the model to pick an action.
        lines = []
        lines.append(f"You are {self.name}, playing the game of Mafia.")
        lines.append(f"Current Phase: {obs.get('phase', 'unknown')}, Day {obs.get('day', 0)}")
        lines.append("Alive Players: " + ", ".join(obs.get("alive_players", [])))
        lines.append("Dead Players: " + ", ".join(obs.get("dead_players", [])))
        lines.append("Recent Messages:")
        for msg in obs.get("messages", []):
            lines.append(f"  - {msg}")
        lines.append("Based on the above, choose your next action in JSON format.")
        lines.append('Example: {"action": "accuse", "target": "Bob"}')

        return "\n".join(lines)

    def parse_action(self, response: str) -> Dict[str, Any]:
        """
        Try to parse the LLM’s output as JSON. If parsing fails or fields are missing,
        default to {"action": "pass"}.
        """
        try:
            data = json.loads(response)
            # Validate minimal structure
            if "action" not in data:
                return {"action": "pass"}
            return data
        except json.JSONDecodeError:
            return {"action": "pass"}
