# === mafia/game_state.py ===

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Any, Union
import uuid

# Core references to your enums, players, and roles:
from llm_games.mafia.enums import GamePhase, Faction
from llm_games.mafia.player import Player
from llm_games.mafia.mechanics.roles import Goon, Godfather, get_role_class

# -------------------------------------------------------------------
# Define the "type" of a single logged message, for clarity.
# Feel free to expand or rename these categories.
# -------------------------------------------------------------------
MESSAGE_TYPES = (
    "system",            # Internal system or phase announcements
    "public",            # Publicly spoken messages
    "whisper",           # Private whisper from A→B
    "vote",              # Voting or accusation messages
    "death_announcement" # Messages triggered on death
    # ... add "debug", "accusation", etc. as you see fit
)

@dataclass
class GameMessage:
    """Structured record of a single game message."""
    msg_type: str       # e.g. 'system', 'public', 'whisper', ...
    sender: str         # 'system' or player_name
    content: str
    recipients: Optional[List[str]] = None  # None means public
    phase: GamePhase = GamePhase.NIGHT
    day: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a serializable dict (helpful if you store logs as JSON)."""
        return {
            "type": self.msg_type,
            "sender": self.sender,
            "content": self.content,
            "recipients": self.recipients,
            "phase": self.phase.name,
            "day": self.day
        }


@dataclass
class GameState:
    """
    Central data store for a Mafia game:
      - Keeps track of players, alive/dead sets, messages, day/night transitions
      - Contains methods for logging and checking endgame
    """

    # ------------------------------
    # Core game setup
    # ------------------------------
    players: List[Player]
    game_config: Dict[str, Any] = field(default_factory=dict)  # e.g. "lynch_required": True, etc.

    # ------------------------------
    # Phase & Turn Tracking
    # ------------------------------
    phase: GamePhase = GamePhase.NIGHT
    day_count: int = 0
    turn_number_in_phase: int = 0
    current_player_turn: Optional[str] = None

    # Keep track of which players are alive or dead
    alive_players: Set[str] = field(default_factory=set)
    dead_players: Set[str] = field(default_factory=set)

    # ------------------------------
    # Logging
    # ------------------------------
    # Public and private logs
    messages: List[GameMessage] = field(default_factory=list)
    hidden_log: List[Dict[str, Any]] = field(default_factory=list)

    # ------------------------------
    # Accusation / Voting (Day)
    # ------------------------------
    # E.g. for a pre-trial voting system if you use it
    votes_for_accusation: Dict[str, str] = field(default_factory=dict)  # voter -> target
    accusation_counts: Dict[str, int] = field(default_factory=dict)     # target -> count

    # Which player is currently on trial (if any)
    player_on_trial: Optional[str] = None

    # Final-lunch votes: None = abstain, True = Guilty, False = Innocent
    votes_for_lynch: Dict[str, Optional[bool]] = field(default_factory=dict)

    # Token budgets for controlling how much players can speak (optional)
    discussion_token_budgets: Dict[str, int] = field(default_factory=dict)

    # ------------------------------
    # Night Phase Action Tracking
    # ------------------------------
    night_actions_submitted: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    night_action_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # ------------------------------
    # Game Identity & Completion
    # ------------------------------
    game_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    game_over: bool = False
    winner: Optional[Faction] = None
    final_player_roles: Dict[str, str] = field(default_factory=dict)  # e.g. "Alice": "Godfather"

    # Optional: track transitions or time-based info
    phase_history: List[Dict[str, Any]] = field(default_factory=list)

    # ----------------------------------------------------------------
    # Initialization & Setup
    # ----------------------------------------------------------------

    def initialize(self):
        """Called once at game start to populate initial states."""
        self.alive_players = {p.name for p in self.players}
        self.dead_players.clear()
        self.day_count = 0
        self.phase = GamePhase.NIGHT
        self.game_over = False
        self.winner = None
        self.messages.clear()
        self.hidden_log.clear()
        self.final_player_roles.clear()
        self.votes_for_accusation.clear()
        self.accusation_counts.clear()
        self.player_on_trial = None
        self.votes_for_lynch.clear()

        # Reset each player's personal state
        for player in self.players:
            player.reset_for_new_game()
            # Optionally set token budgets if using
            # initial_tokens = self.game_config.get("initial_tokens", 999)
            # self.discussion_token_budgets[player.name] = initial_tokens

        # Example: record the start of the initial phase
        self.record_phase_start()

        # Log game creation
        self.log_message("system", "Game started.", msg_type="system")
        self.log_hidden("system", f"Game ID: {self.game_id}")
        self.log_hidden("system", f"Initial Roles: { {p.name: p.role.name for p in self.players} }")

    # ----------------------------------------------------------------
    # Player & Survival
    # ----------------------------------------------------------------

    def get_player(self, name: str) -> Optional[Player]:
        return next((p for p in self.players if p.name == name), None)

    def is_alive(self, name: str) -> bool:
        return name in self.alive_players

    def kill_player(self, name: str, reason: str = "killed"):
        """
        Officially kills a player:
          - Removes from alive_players
          - Logs death message
          - Checks if Godfather died => Goon promotion
          - Triggers check_game_end
        """
        if name not in self.alive_players:
            return  # Already dead or invalid

        player = self.get_player(name)
        if not player:
            return

        self.alive_players.remove(name)
        self.dead_players.add(name)
        player.alive = False

        self.log_message(
            "system",
            f"{name} ({player.role.name}) has died ({reason}).",
            msg_type="death_announcement"
        )
        self.log_hidden("system", f"{name} died. Reason: {reason}")

        # Check for Godfather death => Promote a Goon
        if isinstance(player.role, Godfather):
            self._promote_goon_to_gf(dead_gf_name=name)

        self.check_game_end()

    def _promote_goon_to_gf(self, dead_gf_name: str):
        """Promote the first alive Goon to Godfather upon GF death."""
        promoted_goon: Optional[Player] = None
        for p in self.players:
            if p.name in self.alive_players and isinstance(p.role, Goon):
                promoted_goon = p
                break

        if promoted_goon:
            new_role = Godfather()
            promoted_goon.role = new_role
            promoted_goon.faction = new_role.faction
            self.log_message(
                "system",
                f"{promoted_goon.name} has been promoted to Godfather!",
                msg_type="system"
            )
            self.log_hidden(
                promoted_goon.name,
                f"Promoted to Godfather after {dead_gf_name}'s death"
            )
        else:
            self.log_hidden("system", f"No Goon available to promote after {dead_gf_name} died.")

    # ----------------------------------------------------------------
    # Phase State Management
    # ----------------------------------------------------------------

    def reset_night_phase_state(self):
        """Clears any leftover actions/results from the previous night phase."""
        self.night_actions_submitted.clear()
        self.night_action_results.clear()
        self.turn_number_in_phase = 0
        self.current_player_turn = None
        for p_name in self.alive_players:
            p = self.get_player(p_name)
            if p:
                p.reset_night_state()

    def reset_day_phase_state(self):
        """Clears day-specific data like accusations, lynch votes, and resets turn tracking."""
        self.votes_for_accusation.clear()
        self.accusation_counts.clear()
        self.player_on_trial = None
        self.votes_for_lynch.clear()
        self.turn_number_in_phase = 0
        self.current_player_turn = None
        for p_name in self.alive_players:
            p = self.get_player(p_name)
            if p:
                p.reset_day_state()

    # ----------------------------------------------------------------
    # Accusation & Voting Threshold
    # ----------------------------------------------------------------

    def update_vote_counts(self, voter: str, old_target: Optional[str], new_target: str):
        """
        If your day logic uses an 'accuse to put on trial' mechanism,
        track each player's accusation and count how many times each target was accused.
        """
        if old_target and old_target in self.accusation_counts:
            self.accusation_counts[old_target] -= 1
            if self.accusation_counts[old_target] <= 0:
                del self.accusation_counts[old_target]

        self.accusation_counts[new_target] = self.accusation_counts.get(new_target, 0) + 1
        self.votes_for_accusation[voter] = new_target

    def get_accusation_threshold(self) -> int:
        """
        Returns how many votes are needed to put someone on trial during discussion.
        By default, we use a majority threshold if not explicitly set.

        e.g. threshold = floor(#alive / 2) + 1
        """
        if "accusation_threshold" in self.game_config:
            return int(self.game_config["accusation_threshold"])
        # Default to simple majority
        return (len(self.alive_players) // 2) + 1

    def accusation_threshold_reached(self, target: str) -> bool:
        """Check if the accused has enough votes to start a trial."""
        needed = self.get_accusation_threshold()
        return self.accusation_counts.get(target, 0) >= needed

    # ----------------------------------------------------------------
    # Night Actions
    # ----------------------------------------------------------------

    def register_night_action(self, actor_name: str, action: Dict[str, Any]):
        """Stores the intended night action from a player. The environment resolves them later."""
        if not self.is_alive(actor_name):
            return
        self.night_actions_submitted[actor_name] = action
        self.log_hidden(actor_name, f"Submitted night action: {action}")

    # ----------------------------------------------------------------
    # Endgame Conditions
    # ----------------------------------------------------------------

    def check_game_end(self) -> bool:
        """
        Checks if the game has ended by evaluating basic Town vs Mafia logic (and optionally expansions).
        If a winner is found, we finalize the game and store final roles.
        """
        if self.game_over:
            return True  # Already ended

        mafia_alive = {p.name for p in self.players if p.alive and p.faction == Faction.MAFIA}
        town_alive = {p.name for p in self.players if p.alive and p.faction == Faction.TOWN}
        # If you want to handle neutrals or special roles, do so here

        winner: Optional[Faction] = None

        # Example: Town wins if no mafia remain
        if not mafia_alive:
            winner = Faction.TOWN
        # Mafia wins if mafia >= town or the config-based rule
        elif len(mafia_alive) >= len(town_alive):
            winner = Faction.MAFIA

        # Add any additional conditions or neutrals logic here

        if winner:
            self.game_over = True
            self.winner = winner
            self.phase = GamePhase.GAME_OVER

            # Final role record
            self.final_player_roles = {p.name: p.role.name for p in self.players}

            self.log_message(
                "system",
                f"Game Over! Winner: {winner.value.upper()}",
                msg_type="system"
            )
            self.log_hidden("system", f"Final Roles: {self.final_player_roles}")
            return True

        return False

    # ----------------------------------------------------------------
    # Logging
    # ----------------------------------------------------------------

    def log_message(self,
                    sender: str,
                    content: str,
                    recipients: Optional[List[str]] = None,
                    msg_type: str = "public"):
        """
        Logs a message to the main game log with a specified type (system, whisper, etc.).
        If 'recipients' is None, it's public for all. Otherwise, only the given recipients can see it.
        """
        if msg_type not in MESSAGE_TYPES:
            msg_type = "public"  # fallback if unknown

        self.messages.append(
            GameMessage(
                msg_type=msg_type,
                sender=sender,
                content=content,
                recipients=recipients,
                phase=self.phase,
                day=self.day_count
            )
        )

    def log_hidden(self, actor: str, info: str):
        """
        Logs details that only certain debugging or hidden channels should see.
        Often used for debugging or system clarifications.
        """
        entry = {
            "actor": actor,
            "info": info,
            "phase": self.phase.name,
            "day": self.day_count,
            "turn": self.turn_number_in_phase
        }
        self.hidden_log.append(entry)

    # ----------------------------------------------------------------
    # Observations
    # ----------------------------------------------------------------

    def get_player_observation(self, player_name: str) -> Dict[str, Any]:
        """
        Generates a viewpoint for one player, including:
        - Visible public (and relevant private) messages.
        - A list of all players with appended status tags:
            * [DEAD]  if the player is eliminated.
            * [On Trial]  if the player is currently on trial.
            * [Mafia] (only visible to mafia players) if the player belongs to the mafia.
        - Other information about the game state.
        """
        player = self.get_player(player_name)
        if not player or not player.alive:
            return {
                "game_id": self.game_id,
                "player_name": player_name,
                "alive": False,
                "message": "You are no longer in the game."
            }

        # Prepare visible messages as before.
        visible_messages: List[str] = []
        for msg_obj in self.messages:
            # Validate the message object type.
            if not isinstance(msg_obj, GameMessage):
                self.log_hidden(player_name, f"Invalid message object (type={type(msg_obj)}): {msg_obj}")
                continue
            is_recip_private = (msg_obj.recipients is not None and player_name in msg_obj.recipients)
            is_sender_private = (msg_obj.sender == player_name and msg_obj.recipients is not None)
            if (msg_obj.recipients is None) or is_recip_private or is_sender_private:
                if msg_obj.msg_type == "whisper":
                    if is_sender_private:
                        visible_messages.append(f"(Whisper to {msg_obj.recipients[0]}) {msg_obj.content}")
                    elif is_recip_private:
                        visible_messages.append(f"(Whisper from {msg_obj.sender}) {msg_obj.content}")
                    else:
                        visible_messages.append(f"{msg_obj.sender}: {msg_obj.content}")
                else:
                    visible_messages.append(f"{msg_obj.sender}: {msg_obj.content}")

        # Create a formatted player list with status indicators.
        player_list = []
        for p in self.players:
            status_tags = []
            # Append [DEAD] if the player is not alive.
            if not p.alive:
                status_tags.append("DEAD")
            # Append [On Trial] if p is the player on trial.
            if self.player_on_trial == p.name:
                status_tags.append("On Trial")
            # If the observing player is Mafia, they see their own team tags.
            observer = self.get_player(player_name)
            if observer.faction == Faction.MAFIA and p.faction == Faction.MAFIA:
                status_tags.append("Mafia")
            # Combine the status tags.
            status_str = " [" + ", ".join(status_tags) + "]" if status_tags else ""
            player_list.append(f"{p.name}{status_str}")

        # Build the final observation dict.
        obs = {
            "game_id": self.game_id,
            "player_name": player.name,
            "role": player.role.name,
            "role_description": player.role.get_role_description(),
            "faction": player.faction.value,
            "phase": self.phase.name,
            "day": self.day_count,
            "turn": self.turn_number_in_phase,
            "is_current_turn": (self.current_player_turn == player.name),
            "alive_players": sorted(list(self.alive_players)),
            "dead_players": sorted(list(self.dead_players)),
            "player_list": player_list,  # Our new formatted player list with statuses
            "messages": visible_messages[-20:],  # Most recent 20 messages
            "can_speak": player.can_speak(),
            "can_act_tonight": (player.can_act_at_night() and self.phase == GamePhase.NIGHT),
            "player_on_trial": self.player_on_trial,
            "votes_for_accusation": dict(self.votes_for_accusation),
            "accusation_counts": dict(self.accusation_counts),
            "memory": list(player.memory),
            "is_roleblocked": player.is_roleblocked,
            "protected_by": player.protected_by,
            "lynch_votes": {voter: val for voter, val in self.votes_for_lynch.items()},
        }
        return obs


    # ----------------------------------------------------------------
    # Optional: Phase Tracking for Debug or Time-Aware Agents
    # ----------------------------------------------------------------

    def record_phase_start(self):
        """
        Record the beginning of a new phase for debugging or analysis.
        You might store timestamps, etc.
        """
        entry = {
            "phase": self.phase.name,
            "day": self.day_count,
            "turn_start": self.turn_number_in_phase,
            "timestamp": None  # set to datetime.now() if you want
        }
        self.phase_history.append(entry)

    def record_phase_end(self):
        """Mark the end of the current phase, e.g. to track how long each phase lasted."""
        if self.phase_history:
            self.phase_history[-1]["turn_end"] = self.turn_number_in_phase
            self.phase_history[-1]["end_timestamp"] = None  # if storing actual time

    # ----------------------------------------------------------------
    # Auditing / Debugging Tools
    # ----------------------------------------------------------------

    def get_game_summary(self) -> Dict[str, Any]:
        """
        Returns a structured summary of the game’s final state or current state.
        Useful for logs, testing, or replay.
        """
        summary = {
            "game_id": self.game_id,
            "phase": self.phase.name,
            "day_count": self.day_count,
            "game_over": self.game_over,
            "winner": self.winner.value if self.winner else None,
            "alive_players": sorted(list(self.alive_players)),
            "dead_players": sorted(list(self.dead_players)),
            "final_player_roles": dict(self.final_player_roles),
            "messages_count": len(self.messages),
            "hidden_log_count": len(self.hidden_log),
            "phase_history": self.phase_history,
        }
        return summary

