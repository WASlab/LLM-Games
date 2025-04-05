import random
from typing import Dict, Any, Optional
from llm_games.mafia.agents.base_agent import BaseAgent

class RuleAgent(BaseAgent):
    """
    A deterministic/strategy-based agent for testing.
    Useful for verifying environment correctness before using complex LLM behavior.
    """
    def __init__(self,
                 name: str,
                 role: Optional[str] = None,
                 strategy: Optional[Dict[str, Any]] = None,
                 seed: Optional[int] = None):
        super().__init__(name)
        self.player_role = (role or "").lower()
        self.strategy = strategy or {}
        self.rng = random.Random(seed)
        self.last_observation: Optional[Dict[str, Any]] = None
        self.max_discussion_turns = self.strategy.get("max_discussion_turns", 2)

    def observe(self, observation: Dict[str, Any]):
        self.last_observation = observation

    def act(self) -> Dict[str, Any]:
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
            return self._fallback_action()

    # ---------- Private Phase Logic ----------

    def _night_action(self) -> Dict[str, Any]:
        
        alive = self.last_observation.get("alive_players", [])
        if not alive:
            return {"action": "pass"}

        if self.player_role == "cop":
            target = self._choose_target(alive)
            return {"action": "investigate", "target": target}
        elif self.player_role == "doctor":
            return {"action": "protect", "target": self.name}
        elif self.player_role == "godfather":
            # Use mafia_members from observation (should be provided to mafia agents)
            mafia_members = self.last_observation.get("mafia_members", [])
            target_candidates = [p for p in alive if p not in mafia_members and p != self.name]
            if not target_candidates:
                return {"action": "pass"}
            target = self._choose_target(target_candidates)
            return {"action": "kill", "target": target}
        return {"action": "pass"}

    def _day_discussion_action(self) -> Dict[str, Any]:
        # Do not accuse if someone is already on trial
        if self.last_observation.get("player_on_trial"):
            return {"action": "pass"}

        # With some probability, issue an accusation (if it's our turn)
        if self.last_observation.get("is_current_turn", False) and self.rng.random() < 0.5:
            alive = self.last_observation.get("alive_players", [])
            if alive:
                target = self._choose_target(alive)
                return {"action": "accuse", "target": target}

        # Otherwise, if it's our turn, speak
        if self.last_observation.get("is_current_turn", False):
            return {"action": "speak", "content": f"{self.name} says something insightful."}

        return {"action": "pass"}

    def _defense_action(self) -> Dict[str, Any]:
        if self.last_observation.get("player_on_trial") == self.name:
            return {"action": "speak", "content": f"{self.name} defends themselves."}
        return {"action": "pass"}

    def _final_vote_action(self) -> Dict[str, Any]:
        if self.strategy.get("always_vote_guilty"):
            return {"action": "vote", "vote_type": "final_guilty"}
        elif self.strategy.get("always_vote_innocent"):
            return {"action": "vote", "vote_type": "final_innocent"}
        choice = self.rng.choice(["final_guilty", "final_innocent", "abstain"])
        return {"action": "vote", "vote_type": choice}

    def _fallback_action(self) -> Dict[str, Any]:
        return {"action": "pass"}

    # ---------- Helpers ----------
    def _choose_target(self, candidates: list) -> str:
        if not candidates:
            return self.name
        return self.rng.choice(candidates)

    @property
    def _alive_players(self) -> list:
        obs_alive = self.last_observation.get("alive_players", [])
        return [p for p in obs_alive if p != self.name]
