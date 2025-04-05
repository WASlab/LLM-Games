# mafia/environment.py
from typing import Dict, List, Optional
from mafia.game_state import GameState
from mafia.player import Player
from mafia.enums import Phase
from mafia.rewards import compute_rewards
from mafia.utils.token_cost import track_tokens

class MafiaEnvironment:
    def __init__(self, players: List[Player]):
        self.state = GameState(players=players)
        self.state.initialize()

    def step(self):
        if self.state.phase == Phase.NIGHT:
            self._resolve_night()
            self._transition_to_day()
        elif self.state.phase == Phase.DAY:
            self._resolve_day()
            self._transition_to_night()
        return self._get_observations(), self.state.ended

    def _resolve_night(self):
        self.state.resolve_night_actions()

    def _transition_to_day(self):
        self.state.phase = Phase.DAY
        self.state.day_count += 1
        self.state.reset_votes()
        self.state.reset_discussion_state()
        for player in self.state.players:
            player.reset_day_state()

    def _resolve_day(self):
        self._process_votes()

    def _transition_to_night(self):
        self.state.phase = Phase.NIGHT
        for player in self.state.players:
            player.reset_night_state()

    def _process_votes(self):
        votes = self.state.voting_targets
        if not votes:
            return
        max_votes = max(votes.values())
        candidates = [name for name, count in votes.items() if count == max_votes]
        if len(candidates) == 1:
            accused = candidates[0]
            self.state.accused_player = accused
            self._process_lynch(accused)

    def _process_lynch(self, accused: str):
        confirm_votes = list(self.state.lynch_confirm_votes.values())
        if not confirm_votes:
            return
        if sum(confirm_votes) > len(confirm_votes) // 2:
            self.state.kill_player(accused)
            self.state.log_hidden(accused, f"Lynched on Day {self.state.day_count}")

    def _get_observations(self) -> Dict[str, Dict]:
        obs = {}
        for player in self.state.players:
            if player.alive:
                obs[player.name] = {
                    "phase": self.state.phase.name,
                    "day": self.state.day_count,
                    "alive": list(self.state.alive_players),
                    "dead": list(self.state.dead_players),
                    "messages": self.state.messages[-10:],
                    "can_speak": player.can_speak(),
                    "accused": self.state.accused_player,
                    "votes": self.state.voting_targets,
                    "token_budget": self.state.discussion_token_budgets.get(player.name, 0)
                }
        return obs

    def act(self, name: str, action: str, target: Optional[str] = None, content: Optional[str] = None):
        player = self.state.get_player(name)
        if not player or not player.alive:
            return False

        success = False
        if action == "accuse" and target:
            success = player.accuse(target, self.state)
        elif action == "predict" and target and content:
            success = player.predict_role(target, content, self.state)
        elif action == "question" and target and content:
            success = player.question(target, content, self.state)
        elif action == "whisper" and target and content:
            success = player.whisper(target, content, self.state)
        elif action == "vote" and target:
            success = player.vote_for(target, self.state)

        if success:
            track_tokens(name, action, content)
        return success

    def apply_rewards(self):
        compute_rewards(self.state)
