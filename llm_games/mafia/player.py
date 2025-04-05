from typing import Optional, Dict, List, Any
# Import the base Role class and Faction enum
from llm_games.mafia.mechanics.roles import Role
from llm_games.mafia.enums import Faction
from llm_games.mafia.mechanics.messaging import GameMessage
# Import GameState for type hinting only to avoid circular dependency
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from llm_games.mafia.game_state import GameState


class Player:
    def __init__(self, name: str, role: Role):
        self.name: str = name
        self.role: Role = role
        # Faction comes directly from the role object
        self.faction: Faction = self.role.faction
        self.alive: bool = True

        # Night action state
        self.night_target: Optional[str] = None  # Who the player chose to target
        self.is_roleblocked: bool = False
        self.protected_by: Optional[str] = None  # Who protected this player (e.g., Doctor's name)

        # Day state
        self.vote: Optional[str] = None  # For initial vote (e.g., accusation target)
        self.trial_vote: Optional[bool] = None  # For final trial vote (True=Guilty, False=Innocent, None=Abstain)
        self.discussion_tokens: int = 0  # Handled by environment/config
        self.can_speak_today: bool = True  # For effects like Blackmailer

        # Action tracking & Memory
        self.has_accused_today: bool = False
        self.predictions: Dict[str, str] = {}  # target_name -> predicted_role_name
        self.questions_asked_today: Dict[str, int] = {}  # target_name -> count
        self.whispers_sent_today: Dict[str, str] = {}  # target_name -> last_whisper_content

        # Memory for roles like Cop (to store investigation results, etc.)
        self.memory: List[Dict[str, Any]] = []

        # Optional: Track messages said/received for advanced agents
        self.messages_said: List[str] = []
        self.messages_received: List[str] = []

    def reset_for_new_game(self):
        """Resets player state for the start of a new game."""
        self.alive = True
        self.reset_night_state()
        self.reset_day_state()
        self.memory.clear()
        self.predictions.clear()
        # Reset message logs if desired
        self.messages_said.clear()
        self.messages_received.clear()

    def reset_night_state(self):
        """Resets state relevant to the night phase."""
        self.night_target = None
        self.is_roleblocked = False
        self.protected_by = None

    def reset_day_state(self):
        """Resets state relevant to the day phase."""
        self.vote = None
        self.trial_vote = None
        # discussion_tokens might be reset by environment based on config
        self.has_accused_today = False
        self.questions_asked_today.clear()
        self.whispers_sent_today.clear()
        self.can_speak_today = True  # Reset mute/blacklist effects

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
        return self.role.night_action(self, game_state, self.night_target)

    def can_speak(self) -> bool:
        """
        Returns whether the player is allowed to speak during the day.
        Can incorporate token budgets or mute effects if needed.
        """
        return self.alive and self.can_speak_today

    # --- Day Actions ---

    def accuse(self, target: str, game_state: 'GameState') -> bool:
        if not self.can_speak():
            self.log_hidden(game_state, f"Attempted to accuse {target} but cannot speak.")
            return False
        target_player = game_state.get_player(target)
        if not target_player or not target_player.alive:
            self.log_hidden(game_state, f"Attempted to accuse {target} but they are dead or invalid.")
            return False

        # Allow re‑accusation: simply log the new accusation
        if self.has_accused_today:
            self.log_hidden(game_state, f"Re‑accusing: updating previous accusation to {target}.")
            # Optionally, update vote counts here if needed (via game_state.update_vote_counts)
        else:
            self.has_accused_today = True

        # Instead of appending a raw string, create a GameMessage.
        game_state.messages.append(GameMessage(
            msg_type="public",
            sender=self.name,
            content=f"{self.name} accuses {target}!",
            recipients=None,
            phase=game_state.phase,
            day=game_state.day_count
        ))
        return True


    def predict_role(self, target: str, predicted_role_name: str, game_state: 'GameState') -> bool:
        """
        Predicts a player's role for internal analysis. Can be used to compare against actual role later.
        """
        if not self.alive:
            return False
        target_player = game_state.get_player(target)
        if not target_player:
            return False

        self.predictions[target] = predicted_role_name
        self.log_hidden(game_state, f"Predicted {target} as {predicted_role_name}")
        return True

    def question(self, target: str, question_text: str, game_state: 'GameState') -> bool:
        """
        Sends a question to another player. The environment typically handles the Q&A flow.
        """
        if not self.can_speak():
            self.log_hidden(game_state, f"Attempted to question {target} but cannot speak.")
            return False
        target_player = game_state.get_player(target)
        if not target_player or not target_player.alive:
            self.log_hidden(game_state, f"Attempted to question {target} but they are dead or invalid.")
            return False

        self.questions_asked_today[target] = self.questions_asked_today.get(target, 0) + 1
        self.log_hidden(game_state, f"Asked {target}: {question_text}")
        game_state.messages.append(f"{self.name} asks {target}: \"{question_text}\"")
        return True

    def whisper(self, target: str, whisper_text: str, game_state: 'GameState') -> bool:
        """
        Sends a private message to another player. The content is hidden from public logs.
        """
        if not self.alive:
            return False
        target_player = game_state.get_player(target)
        if not target_player or not target_player.alive:
            self.log_hidden(game_state, f"Attempted to whisper {target} but they are dead or invalid.")
            return False

        self.whispers_sent_today[target] = whisper_text
        self.log_hidden(game_state, f"Whispered to {target}: {whisper_text}")
        # For simplicity, append a placeholder to public messages (actual content remains hidden)
        game_state.messages.append(f"[WHISPER] {self.name} to {target}")
        return True

    def vote_for(self, target: str, game_state: 'GameState') -> bool:
        """
        Casts or changes a vote during the initial accusation phase.
        """
        if not self.alive:
            return False
        target_player = game_state.get_player(target)
        if not target_player or not target_player.alive:
            self.log_hidden(game_state, f"Attempted to vote for {target} but they are dead or invalid.")
            return False

        old_vote = self.vote
        self.vote = target
        if old_vote and old_vote != target:
            log_msg = f"Changed vote from {old_vote} to {target}"
            public_msg = f"{self.name} changed vote to {target}."
        elif not old_vote:
            log_msg = f"Voted for {target}"
            public_msg = f"{self.name} voted for {target}."
        else:
            return True  # No change needed

        self.log_hidden(game_state, log_msg)
        game_state.messages.append(public_msg)
        game_state.update_vote_counts(self.name, old_vote, target)
        return True

    # --- Voting Phase: Final Trial Vote Support ---
    def cast_trial_vote(self, vote_type: str, game_state: 'GameState') -> bool:
        """
        Casts a final vote during the trial phase.
        vote_type should be one of: 'guilty', 'innocent', 'abstain'.
        This vote is stored separately as trial_vote.
        """
        if not self.alive:
            return False

        vt = vote_type.lower()
        if vt == "guilty":
            self.trial_vote = True
        elif vt == "innocent":
            self.trial_vote = False
        elif vt == "abstain":
            self.trial_vote = None
        else:
            self.log_hidden(game_state, f"Invalid trial vote type: {vote_type}")
            return False

        self.log_hidden(game_state, f"Cast final vote: {vote_type.upper()}")
        game_state.messages.append(f"{self.name} casts a final vote: {vote_type.upper()}.")
        return True

    def abstain_from_vote(self, game_state: 'GameState') -> bool:
        """
        Explicitly abstains from voting in the trial phase.
        """
        if not self.alive:
            return False

        self.trial_vote = None
        self.log_hidden(game_state, "Abstained from voting in the trial phase.")
        game_state.messages.append(f"{self.name} abstains from the final vote.")
        return True

    # --- LLM Action Interface ---
    def get_available_actions(self, game_state: 'GameState') -> List[Dict[str, Any]]:
        """
        Returns a structured list of available actions for this player.
        Each action is represented as a dict with a 'type' and optional 'params'.
        This helps LLM agents know what actions they can take.
        """
        if not self.alive:
            return []

        actions = []

        # Actions available during the day if the player can speak
        if self.can_speak():
            actions.append({"type": "speak", "params": ["content"]})
            actions.append({"type": "accuse", "params": ["target"]})
            actions.append({"type": "question", "params": ["target", "question_text"]})
            actions.append({"type": "predict", "params": ["target", "predicted_role"]})
            actions.append({"type": "whisper", "params": ["target", "whisper_text"]})

        # Actions available during night if the role can act
        if game_state.phase == game_state.phase.__class__.NIGHT and self.can_act_at_night():
            actions.append({"type": "night_action", "params": ["target"]})

        # Voting phase actions (both initial vote and trial vote)
        if game_state.phase.name in {"VOTING", "FINAL_VOTE"}:
            actions.append({"type": "vote", "params": ["target"]})
            actions.append({"type": "abstain", "params": []})
        # Final trial voting is separate from initial accusations
        if game_state.phase.name == "FINAL_VOTE":
            actions.append({"type": "cast_trial_vote", "params": ["vote_type (guilty/innocent/abstain)"]})

        return actions

    # --- Debugging / Serialization ---
    def to_dict(self) -> Dict[str, Any]:
        """
        Serializes the player's state into a dictionary for debugging or logging purposes.
        """
        return {
            "name": self.name,
            "role": self.role.name,
            "faction": self.faction.value,
            "alive": self.alive,
            "vote": self.vote,
            "trial_vote": self.trial_vote,
            "night_target": self.night_target,
            "memory": self.memory,
            "predictions": self.predictions,
            "questions_asked_today": self.questions_asked_today,
            "whispers_sent_today": self.whispers_sent_today,
        }

    def log_hidden(self, game_state: 'GameState', info: str):
        """
        Logs hidden information to the game state's hidden log.
        """
        game_state.log_hidden(self.name, info)

    def __repr__(self):
        status = 'Dead' if not self.alive else 'Alive'
        return f"<Player: {self.name} | Role: {self.role.name} | Faction: {self.faction.value} | Status: {status}>"
