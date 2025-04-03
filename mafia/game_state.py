# mafia/game_state.py
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from mafia.enums import Phase, RoleType
from mafia.player import Player
from mafia.roles import Godfather
import uuid

@dataclass
class GameState:
    players: List[Player]
    phase: Phase = Phase.NIGHT
    day_count: int = 0
    alive_players: Set[str] = field(default_factory=set)
    dead_players: Set[str] = field(default_factory=set)
    messages: List[str] = field(default_factory=list)
    current_speaker: Optional[str] = None
    voting_targets: Dict[str, int] = field(default_factory=dict)  # name → votes
    accused_player: Optional[str] = None
    lynch_confirm_votes: Dict[str, bool] = field(default_factory=dict)
    discussion_token_budgets: Dict[str, int] = field(default_factory=dict)
    night_actions: Dict[str, Dict] = field(default_factory=dict)  # name → action object
    game_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ended: bool = False
    winner: Optional[str] = None  # 'town', 'mafia', etc.
    hidden_log: List[Dict] = field(default_factory=list)

    def initialize(self):
        """Called at game start to set up the player list and mark everyone alive."""
        self.alive_players = {p.name for p in self.players}
        self.dead_players = set()
        self.day_count = 0
        self.phase = Phase.NIGHT
        for player in self.players:
            player.reset_for_new_game()
            self.discussion_token_budgets[player.name] = 0

    def get_player(self, name: str) -> Optional[Player]:
        for p in self.players:
            if p.name == name:
                return p
        return None

    def is_alive(self, name: str) -> bool:
        return name in self.alive_players

    def kill_player(self, name: str):
        self.alive_players.discard(name)
        self.dead_players.add(name)
        player = self.get_player(name)
        if player:
            player.alive = False
            # Check for Godfather death and promote a Goon
            if player.role.name.lower() == "godfather":
                goons = [
                    p for p in self.players
                    if p.name in self.alive_players and p.role.name.lower() == "goon"
                ]
                if goons:
                    promoted = goons[0]
                    promoted.role = Godfather()
                    self.messages.append(f"{promoted.name} has been promoted to Godfather.")
                    self.log_hidden(promoted.name, f"Promoted to Godfather after {name}'s death")

    def reset_votes(self):
        self.voting_targets.clear()
        self.accused_player = None
        self.lynch_confirm_votes.clear()

    def reset_discussion_state(self):
        self.current_speaker = None
        for name in self.alive_players:
            self.discussion_token_budgets[name] = 0

    def register_night_action(self, actor: str, action: Dict):
        self.night_actions[actor] = action

    def resolve_night_actions(self):
        # Placeholder for role-based resolution logic
        pass

    def check_game_end(self) -> bool:
        mafia = [p for p in self.players if p.alive and p.role.alignment == 'mafia']
        town = [p for p in self.players if p.alive and p.role.alignment == 'town']

        if not mafia:
            self.ended = True
            self.winner = 'town'
        elif len(mafia) >= len(town):
            self.ended = True
            self.winner = 'mafia'

        return self.ended

    def log_hidden(self, actor: str, info: str):
        self.hidden_log.append({
            "tick": self.day_count,
            "actor": actor,
            "info": info
        })
