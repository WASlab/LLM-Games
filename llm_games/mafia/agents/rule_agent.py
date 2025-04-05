# === mafia/agents/rule_agent.py ===

import random
from typing import Dict, Any, Optional
from llm_games.mafia.agents.base_agent import BaseAgent

class RuleAgent(BaseAgent):
    """
    A deterministic or strategy-driven agent for testing.
    Useful for verifying environment correctness before introducing complex LLM behavior.
    """
    def __init__(self,
                 name: str,
                 player_role: Optional[str] = None,
                 strategy: Optional[Dict[str, Any]] = None,
                 seed: Optional[int] = None):
        """
        :param name:         Agent/player name
        :param player_role:  The role name (Cop, Doctor, etc.) for simple logic
        :param strategy:     A dictionary describing special behaviors (e.g. always_accuse)
        :param seed:         Optional seed for reproducible random choices
        """
        super().__init__(name)
        self.player_role = (player_role or "").lower()
        self.strategy = strategy or {}
        self.last_observation: Optional[Dict[str, Any]] = None
        self.rng = random.Random(seed)

    def observe(self, observation: Dict[str, Any]):
        """Store the latest game observation for decision making."""
        self.last_observation = observation

    def act(self) -> Dict[str, Any]:
        """
        Decide on an action based on the last observation and the agent’s
        role/strategy. Returns a dict like {"action": "accuse", "target": "Bob"}.
        """
        if not self.last_observation:
            return {"action": "pass"}

        phase = self.last_observation.get("phase", "").lower()

        if phase == "night":
            return self._night_action()
        elif phase == "day_discussion":
            return self._day_discussion_action()
        elif phase == "defense":
            return self._defense_action()
        elif phase == "final_vote":
            return self._final_vote_action()
        else:
            # voting or unknown phase → pass
            return self._fallback_action()

    # ------------------ Private Phase Logic ------------------

    def _night_action(self) -> Dict[str, Any]:
        """
        Basic logic for roles at night:
          - Cop: investigate a random alive target
          - Doctor: protect self
          - Godfather: kill a random target outside mafia
          - else pass
        """
        if not self._alive_players:
            return {"action": "pass"}

        if self.player_role == "cop":
            target = self._choose_target(self._alive_players)
            return {"action": "investigate", "target": target}
        elif self.player_role == "doctor":
            # e.g., always protect self
            return {"action": "protect", "target": self.name}
        elif self.player_role == "godfather":
            # choose random non-mafia if possible
            # if you have a list of mafia members, avoid them
            mafia_members = self.last_observation.get("mafia_members", [])
            target_candidates = [p for p in self._alive_players if p not in mafia_members and p != self.name]
            if not target_candidates:
                return {"action": "pass"}
            chosen = self._choose_target(target_candidates)
            return {"action": "kill", "target": chosen}
        return {"action": "pass"}

    def _day_discussion_action(self) -> Dict[str, Any]:
        """
        Basic day logic:
          - Possibly accuse if strategy says always_accuse
          - If it's your turn (is_current_turn), speak
          - else pass
        """
        # If there's already a player on trial, do nothing
        if self.last_observation.get("player_on_trial"):
            return {"action": "pass"}

        # Possibly accuse if strategy says so
        if self.strategy.get("always_accuse", False):
            # pick a random target from alive
            if self._alive_players:
                target = self._choose_target(self._alive_players)
                return {"action": "accuse", "target": target}

        # If it's my turn to speak, say something
        if self.last_observation.get("is_current_turn", False):
            return {"action": "speak", "content": f"{self.name} says hello."}

        return {"action": "pass"}

    def _defense_action(self) -> Dict[str, Any]:
        """
        If I'm on trial, present a defense; otherwise pass.
        """
        # If I'm on trial, we provide a 'defense' speech
        if self.last_observation.get("player_on_trial") == self.name:
            return {"action": "speak", "content": f"{self.name} defends themselves."}
        return {"action": "pass"}

    def _final_vote_action(self) -> Dict[str, Any]:
        """
        Final vote logic. We can either always vote guilty/innocent or random:
        """
        if self.strategy.get("always_vote_guilty"):
            return {"action": "vote", "vote_type": "final_guilty"}
        elif self.strategy.get("always_vote_innocent"):
            return {"action": "vote", "vote_type": "final_innocent"}

        # random choice if no strategy
        choice = self.rng.choice(["final_guilty", "final_innocent", "abstain"])
        return {"action": "vote", "vote_type": choice}

    def _fallback_action(self) -> Dict[str, Any]:
        """
        If we’re in a voting phase or unknown, pass or skip.
        """
        return {"action": "pass"}

    # ------------------ Helper Methods ------------------

    def _choose_target(self, candidates: list) -> str:
        """
        Returns a single candidate from the list, using deterministic
        or seeded randomness.
        """
        if not candidates:
            return self.name  # fallback to self
        return self.rng.choice(candidates)

    @property
    def _alive_players(self) -> list:
        """Returns a list of alive players (minus self)."""
        obs_alive = self.last_observation.get("alive_players", [])
        return [p for p in obs_alive if p != self.name]
