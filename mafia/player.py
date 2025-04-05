from typing import Optional, Dict, List, Any
# Import the base Role class and Faction enum
from mafia.mechanics.roles import Role
from mafia.enums import Faction
# Import GameState for type hinting only to avoid circular dependency
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from mafia.game_state import GameState


class Player:
    # Role hint uses the class, not the enum
    def __init__(self, name: str, role: Role):
        self.name: str = name
        self.role: Role = role
        # Faction comes directly from the role object
        self.faction: Faction = self.role.faction
        self.alive: bool = True

        # Night action state
        self.night_target: Optional[str] = None # Who the player chose to target
        self.is_roleblocked: bool = False
        self.protected_by: Optional[str] = None # Who protected this player (e.g., Doctor's name)

        # Day state
        self.vote: Optional[str] = None
        self.discussion_tokens: int = 0 # Handled by environment/config
        self.can_speak_today: bool = True # For effects like Blackmailer

        # Action tracking & Memory
        self.has_accused_today: bool = False
        self.predictions: Dict[str, str] = {} # target_name -> predicted_role_name
        self.questions_asked_today: Dict[str, int] = {} # target_name -> count
        self.whispers_sent_today: Dict[str, str] = {} # target_name -> last_whisper_content
        # Memory for roles like Cop
        self.memory: List[Dict[str, Any]] = []

    def reset_for_new_game(self):
        """Resets player state for the start of a new game."""
        self.alive = True
        self.reset_night_state()
        self.reset_day_state()
        self.memory.clear()
        self.predictions.clear()
        # Role is assigned at init, faction derives from it

    def reset_night_state(self):
        """Resets state relevant to the night phase."""
        self.night_target = None
        self.is_roleblocked = False
        self.protected_by = None

    def reset_day_state(self):
        """Resets state relevant to the day phase."""
        self.vote = None
        # discussion_tokens might be reset by environment based on config
        self.has_accused_today = False
        self.questions_asked_today.clear()
        self.whispers_sent_today.clear()
        self.can_speak_today = True # Reset blacklist effect

    def can_act_at_night(self) -> bool:
        """Check if player is alive and their role has a night action."""
        return self.alive and self.role.can_act_at_night()

    def perform_night_action(self, game_state: 'GameState') -> Optional[Dict[str, Any]]:
        """
        Performs the player's role-specific night action.
        Assumes self.night_target has been set by the agent.
        Returns the action dict or None.
        """
        if not self.can_act_at_night() or self.is_roleblocked:
            if self.is_roleblocked:
                 self.log_hidden(game_state, "Tried to act but was roleblocked.")
            return None
        # Pass the chosen target to the role's action method
        return self.role.night_action(self, game_state, self.night_target)

    def can_speak(self) -> bool:
        # Add check for blacklist/mute effects
        return self.alive and self.can_speak_today # Add token check if using budgets: and self.discussion_tokens > 0

    # --- Day Actions ---
    # Note: These methods now mostly validate and log,
    # the core logic resides in the Environment or GameState update methods.

    def accuse(self, target: str, game_state: 'GameState'):
        if not self.can_speak() or self.has_accused_today:
            self.log_hidden(game_state, f"Attempted to accuse {target} but couldn't (already accused or cannot speak).")
            return False
        target_player = game_state.get_player(target)
        if not target_player or not target_player.alive:
            self.log_hidden(game_state, f"Attempted to accuse {target} but they are dead or invalid.")
            return False

        # Logic to handle accusation (e.g., trigger voting phase) should be in Environment/GameState
        self.log_hidden(game_state, f"Accused {target}")
        game_state.messages.append(f"{self.name} accuses {target}!")
        self.has_accused_today = True # Limit accusations if desired
        return True

    def predict_role(self, target: str, predicted_role_name: str, game_state: 'GameState'):
        # Prediction is mainly for agent's internal state or analysis
        if not self.alive: return False
        target_player = game_state.get_player(target)
        if not target_player: return False # Predict only existing players

        self.predictions[target] = predicted_role_name
        self.log_hidden(game_state, f"Predicted {target} as {predicted_role_name}")
        # Optional: Public message? game_state.messages.append(f"{self.name} predicts {target} is a {predicted_role_name}.")
        return True

    def question(self, target: str, question_text: str, game_state: 'GameState'):
        if not self.can_speak():
             self.log_hidden(game_state, f"Attempted to question {target} but cannot speak.")
             return False
        target_player = game_state.get_player(target)
        if not target_player or not target_player.alive:
            self.log_hidden(game_state, f"Attempted to question {target} but they are dead or invalid.")
            return False

        # Actual questioning/response logic handled by environment turn manager + agents
        self.questions_asked_today[target] = self.questions_asked_today.get(target, 0) + 1
        # self.discussion_tokens -= 1 # Decrement if using token budgets
        self.log_hidden(game_state, f"Asked {target}: {question_text}")
        game_state.messages.append(f"{self.name} asks {target}: \"{question_text}\"")
        return True

    def whisper(self, target: str, whisper_text: str, game_state: 'GameState'):
        # Whispering might have specific rules (e.g., only Mafia, limits)
        if not self.alive: return False
        target_player = game_state.get_player(target)
        if not target_player or not target_player.alive:
            self.log_hidden(game_state, f"Attempted to whisper {target} but they are dead or invalid.")
            return False

        # Check game rules for whisper permissions if needed
        # e.g., if self.faction != Faction.MAFIA and not game_state.config.allow_all_whispers: return False

        self.whispers_sent_today[target] = whisper_text
        self.log_hidden(game_state, f"Whispered to {target}: {whisper_text}")
        # Add to messages, but potentially filtered based on recipient
        # Using a dedicated messaging system is better here. Assume game_state.messages is public for now.
        game_state.messages.append(f"[WHISPER] {self.name} to {target}") # Content hidden in public log
        # Need a way for target agent to see the whisper content in their observation
        return True

    def vote_for(self, target: str, game_state: 'GameState'):
        if not self.alive: return False
        # Allow voting for dead players? Assume no for now.
        target_player = game_state.get_player(target)
        if not target_player or not target_player.alive:
             self.log_hidden(game_state, f"Attempted to vote for {target} but they are dead or invalid.")
             return False

        # Actual vote tallying happens in GameState/Environment
        old_vote = self.vote
        self.vote = target
        if old_vote and old_vote != target:
            log_msg = f"Changed vote from {old_vote} to {target}"
            public_msg = f"{self.name} changed vote to {target}."
        elif not old_vote:
            log_msg = f"Voted for {target}"
            public_msg = f"{self.name} voted for {target}."
        else: # Voted for same person again
            return True # No change needed

        self.log_hidden(game_state, log_msg)
        game_state.messages.append(public_msg)
        # Signal environment to update vote counts
        game_state.update_vote_counts(self.name, old_vote, target)
        return True

    def log_hidden(self, game_state: 'GameState', info: str):
        """Logs information to the game's hidden log associated with this player."""
        # Ensure game_state has this method or handle logging directly
        game_state.log_hidden(self.name, info)


    def __repr__(self):
        status = 'Dead' if not self.alive else 'Alive'
        return f"<Player: {self.name} | Role: {self.role.name} | Faction: {self.faction.value} | Status: {status}>"
