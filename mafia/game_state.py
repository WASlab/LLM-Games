from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Any
# Use correct imports based on unified role system
from mafia.enums import GamePhase, Faction
from mafia.player import Player
# Import specific role classes only if needed for specific logic (like promotion)
from mafia.mechanics.roles import Goon, Godfather, get_role_class # Added get_role_class
import uuid

@dataclass
class GameState:
    players: List[Player]
    game_config: Dict[str, Any] = field(default_factory=dict) # For rules like godfather_detectable
    phase: GamePhase = GamePhase.NIGHT
    day_count: int = 0
    turn_number_in_phase: int = 0 # Track turns within day/night
    current_player_turn: Optional[str] = None # Whose turn it is to act

    alive_players: Set[str] = field(default_factory=set)
    dead_players: Set[str] = field(default_factory=set)

    messages: List[Dict[str, Any]] = field(default_factory=list) # Store message dicts, not just strings
    hidden_log: List[Dict[str, Any]] = field(default_factory=list)

    # Day phase state
    votes_for_accusation: Dict[str, str] = field(default_factory=dict) # voter -> target
    accusation_counts: Dict[str, int] = field(default_factory=dict) # target -> count
    player_on_trial: Optional[str] = None
    votes_for_lynch: Dict[str, bool] = field(default_factory=dict) # voter -> guilty (True) or innocent (False)

    # Discussion state
    discussion_token_budgets: Dict[str, int] = field(default_factory=dict) # Optional

    # Night phase state
    # Stores chosen actions before resolution: player_name -> {"action_type": "kill", "target": "PlayerB", ...}
    night_actions_submitted: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # Stores resolved outcomes of actions: player_name -> {"action_type": "investigate", "result": "mafia", ...}
    night_action_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)


    game_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    game_over: bool = False
    winner: Optional[Faction] = None # Store winning Faction enum
    final_player_roles: Dict[str, str] = field(default_factory=dict) # player_name -> role_name

    def initialize(self):
        """Called at game start to set up."""
        self.alive_players = {p.name for p in self.players}
        self.dead_players = set()
        self.day_count = 0
        self.phase = GamePhase.NIGHT # Start at night
        self.game_over = False
        self.winner = None
        self.messages.clear()
        self.hidden_log.clear()
        self.final_player_roles.clear()

        # Initialize player states
        for player in self.players:
            player.reset_for_new_game()
            # Set initial token budgets based on config if needed
            # self.discussion_token_budgets[player.name] = self.game_config.get("initial_tokens", 0)

        self.log_message("system", "Game started.")
        self.log_hidden("system", f"Game ID: {self.game_id}")
        self.log_hidden("system", f"Initial Roles: { {p.name: p.role.name for p in self.players} }")


    def get_player(self, name: str) -> Optional[Player]:
        for p in self.players:
            if p.name == name:
                return p
        return None

    def is_alive(self, name: str) -> bool:
        return name in self.alive_players

    def kill_player(self, name: str, reason: str = "killed"):
        """Marks a player as dead and handles consequences like GF promotion."""
        if name not in self.alive_players:
            return # Already dead or invalid

        player = self.get_player(name)
        if not player: return # Should not happen

        self.alive_players.discard(name)
        self.dead_players.add(name)
        player.alive = False
        self.log_message("system", f"{name} ({player.role.name}) has died ({reason}).")
        self.log_hidden("system", f"{name} died. Reason: {reason}")

        # Check for Godfather death and promote a Goon
        if isinstance(player.role, Godfather):
            # Find the first alive Goon to promote
            promoted_goon: Optional[Player] = None
            for p in self.players:
                 # Check using isinstance and ensure they are alive
                if p.name in self.alive_players and isinstance(p.role, Goon):
                    promoted_goon = p
                    break

            if promoted_goon:
                # Change the role object of the promoted player
                new_role = Godfather()
                promoted_goon.role = new_role
                promoted_goon.faction = new_role.faction # Ensure faction is updated if needed
                msg = f"{promoted_goon.name} has been promoted to Godfather!"
                self.log_message("system", msg)
                self.log_hidden(promoted_goon.name, f"Promoted to Godfather after {name}'s death")
            else:
                 self.log_hidden("system", f"Godfather {name} died, but no Goons available to promote.")

        # Check for game end after death
        self.check_game_end()


    def reset_night_phase_state(self):
        self.night_actions_submitted.clear()
        self.night_action_results.clear()
        self.turn_number_in_phase = 0
        self.current_player_turn = None
        for p_name in self.alive_players:
            player = self.get_player(p_name)
            if player: player.reset_night_state()


    def reset_day_phase_state(self):
        self.votes_for_accusation.clear()
        self.accusation_counts.clear()
        self.player_on_trial = None
        self.votes_for_lynch.clear()
        self.turn_number_in_phase = 0
        self.current_player_turn = None # Or set to first speaker
        for p_name in self.alive_players:
            player = self.get_player(p_name)
            if player: player.reset_day_state()

    def update_vote_counts(self, voter: str, old_target: Optional[str], new_target: str):
        """Updates accusation counts when a vote changes."""
        if old_target and old_target in self.accusation_counts:
            self.accusation_counts[old_target] -= 1
            if self.accusation_counts[old_target] <= 0:
                del self.accusation_counts[old_target]

        self.accusation_counts[new_target] = self.accusation_counts.get(new_target, 0) + 1
        self.votes_for_accusation[voter] = new_target


    def register_night_action(self, actor_name: str, action: Dict[str, Any]):
        """Stores the intended night action from a player."""
        if not self.is_alive(actor_name): return
        self.night_actions_submitted[actor_name] = action
        self.log_hidden(actor_name, f"Submitted night action: {action}")

    # resolve_night_actions is now primarily handled by the Environment

    def check_game_end(self) -> bool:
        """Checks if a win condition has been met."""
        if self.game_over: return True # Already ended

        mafia_alive = {p.name for p in self.players if p.alive and p.faction == Faction.MAFIA}
        town_alive = {p.name for p in self.players if p.alive and p.faction == Faction.TOWN}
        # Add other factions (Neutral) if they exist

        winner = None
        if not mafia_alive:
            winner = Faction.TOWN # Town wins if all Mafia are dead
        elif len(mafia_alive) >= len(town_alive):
            # Mafia wins if they equal or outnumber Town (or if only Mafia remain)
            winner = Faction.MAFIA

        # Add neutral win conditions here if applicable

        if winner:
            self.game_over = True
            self.winner = winner
            self.phase = GamePhase.GAME_OVER
            self.log_message("system", f"Game Over! Winner: {winner.value.upper()}")
            self.final_player_roles = {p.name: p.role.name for p in self.players}
            self.log_hidden("system", f"Final Roles: {self.final_player_roles}")
            return True

        return False

    def log_message(self, sender: str, content: str, recipients: Optional[List[str]] = None):
        """Logs a message to the public game log."""
        # Recipients = None means public message
        msg = {"sender": sender, "content": content, "recipients": recipients, "phase": self.phase, "day": self.day_count}
        self.messages.append(msg)

    def log_hidden(self, actor: str, info: str):
        """Logs information relevant to a specific actor or system process."""
        log_entry = {
            "actor": actor,
            "info": info,
            "phase": self.phase,
            "day": self.day_count,
            "turn": self.turn_number_in_phase
        }
        self.hidden_log.append(log_entry)

    def get_player_observation(self, player_name: str) -> Dict[str, Any]:
         """Generates the observation dictionary for a specific player."""
         player = self.get_player(player_name)
         if not player or not player.alive:
             return {} # Or return a specific "you are dead" state

         # Filter messages visible to this player
         visible_messages = []
         for msg in self.messages:
             # Public messages or whispers sent to/by the player
             is_recipient = msg["recipients"] is None or player_name in msg["recipients"]
             is_sender = msg["sender"] == player_name and msg["recipients"] is not None # Show own whispers
             if is_recipient or is_sender:
                 # Maybe format message differently if whisper?
                 if msg["recipients"] and len(msg["recipients"]) == 1 and is_recipient and not is_sender:
                     formatted_content = f"(Whisper from {msg['sender']}): {msg['content']}"
                 elif is_sender:
                     formatted_content = f"(Whisper to {msg['recipients'][0]}): {msg['content']}"
                 else:
                      formatted_content = f"{msg['sender']}: {msg['content']}"
                 visible_messages.append(formatted_content)

         # Include relevant game state info
         obs = {
             "game_id": self.game_id,
             "player_name": player.name,
             "role": player.role.name,
             "role_description": player.role.get_role_description(),
             "faction": player.faction.value,
             "phase": self.phase.name,
             "day": self.day_count,
             "turn": self.turn_number_in_phase,
             "is_current_turn": self.current_player_turn == player.name,
             "alive_players": sorted(list(self.alive_players)),
             "dead_players": sorted(list(self.dead_players)),
             # Provide recent messages
             "messages": visible_messages[-20:], # Limit history size
             "can_speak": player.can_speak(),
             "can_act_tonight": player.can_act_at_night() and self.phase == GamePhase.NIGHT,
             "player_on_trial": self.player_on_trial,
             "votes_for_accusation": self.votes_for_accusation, # {voter: target}
             "accusation_counts": self.accusation_counts,     # {target: count}
             # "token_budget": self.discussion_token_budgets.get(player.name, 0), # If using tokens
             "memory": player.memory, # Include cop results, etc.
             "is_roleblocked": player.is_roleblocked, # Let player know if blocked last night
             "protected_by": player.protected_by, # Let player know if protected last night
         }
         return obs