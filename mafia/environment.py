# === mafia/environment.py ===

import random
from collections import deque
from typing import Dict, List, Optional, Any, Tuple, Set

# Core project imports (ensure they match your directory structure)
from mafia.game_state import GameState
from mafia.player import Player
from mafia.enums import GamePhase, Faction, VoteType
from mafia.mechanics.roles import Cop, Godfather, Roleblocker,Doctor
# If you have a RoleBlocker or Blackmailer, import them similarly:
# from mafia.mechanics.roles import RoleBlocker, Blackmailer

# from mafia.rewards import compute_rewards  # If/when using a reward system
# from mafia.utils.token_cost import track_tokens  # If/when tracking token budgets

# Dummy placeholders if those modules are not yet implemented:
def compute_rewards(state) -> Dict[str, float]:
    """Placeholder if you have not implemented rewards yet."""
    return {}

class TokenTracker:
    """Placeholder if you want to track tokens or verbosity budgets."""
    def __init__(self):
        self.usage = {}

    def update(self, *args, **kwargs):
        pass

    def to_dict(self):
        return dict(self.usage)


class MafiaEnvironment:
    """
    Manages the overall flow, phases, action resolution, and messaging for a Mafia game.

    Key Features:
      - Night action resolution with roleblock → protect → kill → investigate ordering
      - Day discussion with round-robin speaking, optional questioning, accusations
      - Voting phases, including defense and final vote
      - Tie votes or lack of majority → no lynch → transition to Night
      - Basic checks for valid night targets (e.g., Godfather cannot target a fellow Mafia)
    """

    def __init__(self, players: List[Player], config: Dict[str, Any]):
        """
        :param players: Pre-created list of Player objects with assigned roles.
        :param config:  Dictionary of configuration options (e.g. 'lynch_defense_enabled', etc.).
        """
        self.config = config

        # Initialize the game state
        self.state = GameState(players=players, game_config=config)
        self.state.initialize()

        # Token/budget tracking if desired
        self.token_tracker = TokenTracker()

        # Various environment configs
        self.lynch_defense_enabled: bool = self.config.get("lynch_defense_enabled", True)
        self.cop_speaks_first: bool = self.config.get("cop_speaks_first", False)

        # Day phase tracking
        self._speaker_queue: deque[str] = deque()
        # Queue of (questioner, questioned) to handle immediate back-and-forth:
        self._question_queue: deque[Tuple[str, str]] = deque()
        self._turns_taken_this_round: Set[str] = set()
        self._consecutive_passes: int = 0

    # ----------------------------------------------------------------
    # Public Methods for Simulation Loop
    # ----------------------------------------------------------------

    def step_phase(self) -> bool:
        """
        Advances the game by one phase (e.g., from Night → Day or running the defense → final vote).
        Returns True if the game has ended, False otherwise.
        """
        if self.state.game_over:
            return True

        current_phase = self.state.phase

        if current_phase == GamePhase.NIGHT:
            self._resolve_night()
            self._transition_to_day()

        elif current_phase == GamePhase.DAY_DISCUSSION:
            # The discussion-phase turns are advanced by process_player_action or advance_turn.
            # step_phase can check if we need to end discussion automatically.
            if self._check_discussion_end():
                self._transition_to_voting()

        elif current_phase == GamePhase.VOTING:
            # In a simpler design, voting might be resolved automatically or by some timer logic.
            # Often, you transition out of VOTING once everyone has voted, but that can be
            # handled in process_player_action or an external runner. So we just do a no-op here.
            pass

        elif current_phase == GamePhase.DEFENSE:
            # Let the accused speak; then move on to final vote.
            self._run_defense()
            self._transition_to_final_vote()

        elif current_phase == GamePhase.FINAL_VOTE:
            # Once final votes are in (or forced), resolve lynch.
            self._resolve_lynch()
            self._transition_to_night()

        return self.state.check_game_end()

    def get_current_player_name(self) -> Optional[str]:
        """Returns the name of the player whose turn it is to act (during DAY_DISCUSSION)."""
        return self.state.current_player_turn

    def get_observation(self, player_name: str) -> Dict[str, Any]:
        """Returns an observation dict for the specified player (public messages, private info, etc.)."""
        return self.state.get_player_observation(player_name)

    def process_player_action(self, player_name: str, action: Dict[str, Any]) -> bool:
        """
        The main method for handling actions from a player's agent.
        Returns True if the action was processed successfully, False if invalid.
        """
        player = self.state.get_player(player_name)
        if not player or not player.alive:
            self.state.log_hidden(player_name, f"Ignored action {action}; player is dead or invalid.")
            return False

        # Check if it is actually this player's turn (in discussion) or if we allow free actions
        if self.state.phase == GamePhase.DAY_DISCUSSION:
            if self.state.current_player_turn != player_name:
                self.state.log_hidden(
                    player_name, 
                    f"Attempted action {action} but it is not {player_name}'s turn."
                )
                return False

        # Log the attempt
        self.state.log_hidden(player_name, f"Received action: {action}")
        action_type = action.get("action")
        target = action.get("target")
        content = action.get("content")
        self.token_tracker.update(player_name, action_type, content)

        success = False

        # ----------------------------------------------------------------
        # NIGHT ACTIONS
        # ----------------------------------------------------------------
        if self.state.phase == GamePhase.NIGHT:
            if player.can_act_at_night():
                # The player's role logic typically sets a night_action dict or returns None if invalid.
                player.night_target = target
                intended_action = player.perform_night_action(self.state)

                # Optionally, we enforce extra checks (e.g., Godfather cannot target mafia).
                intended_action = self._validate_night_action(player, intended_action)

                if intended_action:
                    self.state.register_night_action(player_name, intended_action)
                success = True  # We treat it as a valid "turn" even if no action is performed.
            else:
                self.state.log_hidden(player_name, "Tried to act at night but this role has no night action.")
                success = True

        # ----------------------------------------------------------------
        # DAY ACTIONS - Discussion Phase
        # ----------------------------------------------------------------
        elif self.state.phase == GamePhase.DAY_DISCUSSION:
            success = self._process_day_discussion_action(player, action_type, target, content)

            # If the action was valid, move to next speaker (unless an immediate phase transition happens).
            if success and not self.state.player_on_trial:
                # If an accusation occurs, we transition to voting within the same turn, so skip advance_turn
                self.advance_turn()

        # ----------------------------------------------------------------
        # VOTING PHASE
        # ----------------------------------------------------------------
        elif self.state.phase == GamePhase.VOTING:
            success = self._process_voting_phase_action(player, action_type, target, content)

        # ----------------------------------------------------------------
        # DEFENSE PHASE
        # ----------------------------------------------------------------
        elif self.state.phase == GamePhase.DEFENSE:
            if player_name == self.state.player_on_trial:
                # The accused can make a statement (content) or pass
                if content:
                    self.state.log_message(player_name, f"(Defense) {content}")
                else:
                    self.state.log_message(player_name, "(Defense) [No statement provided]")
                success = True
            else:
                self.state.log_hidden(player_name, f"Not on trial; ignoring defense action.")
                success = False

        # ----------------------------------------------------------------
        # FINAL VOTE PHASE
        # ----------------------------------------------------------------
        elif self.state.phase == GamePhase.FINAL_VOTE:
            success = self._process_final_vote_action(player, action)

        # ----------------------------------------------------------------
        # If action was valid but the day discussion is still ongoing, 
        # we might want to continue or see if we transition to next phase.
        # ----------------------------------------------------------------
        if not success:
            self.state.log_hidden(player_name, f"Action {action} could not be processed.")
        return success

    def advance_turn(self):
        """
        Advances to the next person's turn in the DAY_DISCUSSION phase,
        respecting any question queue ordering (the questioned player, then questioner’s response).
        """
        if self.state.phase != GamePhase.DAY_DISCUSSION:
            self.state.current_player_turn = None
            return

        # If we have a question queue, that takes priority
        if self._question_queue:
            questioner, questioned = self._question_queue.popleft()
            # The questioned player goes first
            self.state.current_player_turn = questioned
            self.state.turn_context = {"answering_question_from": questioner}

            # Then queue the questioner as next (a short follow-up), unless questioner == questioned
            if questioner != questioned:
                self._question_queue.appendleft((questioner, questioner))
            return

        # If the main speaker queue is empty, check discussion end or start a new round
        if not self._speaker_queue or self._consecutive_passes >= len(self.state.alive_players):
            self._transition_to_voting()
            return

        next_speaker = self._speaker_queue.popleft()
        self.state.current_player_turn = next_speaker
        self.state.turn_number_in_phase += 1
        self.state.turn_context = None

    # ----------------------------------------------------------------
    # Internal / Private Helpers
    # ----------------------------------------------------------------

    def _resolve_night(self):
        """Resolves all players' night actions in the correct order (roleblock, protect, kill, investigate, etc.)."""
        self.state.log_message("system", "Night ends. Resolving all night actions...")
        self.state.night_action_results.clear()
        submitted_actions = self.state.night_actions_submitted

        # 1. Roleblocks
        roleblocked_players: Set[str] = set()
        # 2. Blackmail
        blackmailed_players: Set[str] = set()

        for actor, action_dict in submitted_actions.items():
            if not self.state.is_alive(actor):
                continue  # Actor died mid-night somehow

            # e.g. if action_dict["type"] == "roleblock": ...
            # Example placeholder:
            if action_dict.get("type") == "roleblock":
                target = action_dict.get("target")
                if target and self.state.is_alive(target):
                    roleblocked_players.add(target)
                    self.state.log_hidden(
                        actor, f"Roleblocked {target} for the night."
                    )
            elif action_dict.get("type") == "blackmail":
                target = action_dict.get("target")
                if target and self.state.is_alive(target):
                    blackmailed_players.add(target)
                    self.state.log_hidden(actor, f"Blackmailed {target} for the day.")

        # Mark roleblocked players
        for blocked in roleblocked_players:
            p = self.state.get_player(blocked)
            if p:
                p.is_roleblocked = True

        # Mark blackmailed players so they can't speak tomorrow
        for bm in blackmailed_players:
            p = self.state.get_player(bm)
            if p:
                p.can_speak_today = False

        # 3. Protections
        protected: Dict[str, str] = {}
        for actor, action_dict in submitted_actions.items():
            if actor in roleblocked_players:
                continue
            if not self.state.is_alive(actor):
                continue
            if action_dict.get("type") == "protect":
                target = action_dict.get("target")
                if target and self.state.is_alive(target):
                    # If multiple doctors protect the same target, the first or last might "win."
                    # Here we allow the first to stand; you can choose whichever convention you like.
                    if target not in protected:
                        protected[target] = actor
                        # For debug or future logic
                        target_p = self.state.get_player(target)
                        if target_p:
                            target_p.protected_by = actor
                        self.state.log_hidden(
                            actor, f"Protected {target} this night."
                        )

        # 4. Kills
        kills_attempted: List[Tuple[str, str]] = []
        for actor, action_dict in submitted_actions.items():
            if actor in roleblocked_players:
                continue
            if not self.state.is_alive(actor):
                continue
            if action_dict.get("type") == "kill":
                target = action_dict.get("target")
                if target and self.state.is_alive(target):
                    kills_attempted.append((actor, target))
                    self.state.log_hidden(actor, f"Attempting kill on {target}.")

        successful_kills: Set[str] = set()
        for (killer, target) in kills_attempted:
            if target not in protected:
                successful_kills.add(target)
                self.state.log_hidden(killer, f"Kill on {target} succeeded.")
            else:
                doc = protected[target]
                self.state.log_hidden(killer, f"Kill on {target} failed (protected by {doc}).")
                self.state.log_hidden(doc, f"You successfully protected {target} from a kill.")

        # Apply kills
        deaths = []
        for victim in successful_kills:
            if self.state.is_alive(victim):
                self.state.kill_player(victim, reason="killed during night")
                deaths.append(victim)

        # 5. Investigations
        for actor, action_dict in submitted_actions.items():
            if actor in roleblocked_players:
                continue
            if not self.state.is_alive(actor):
                continue
            if action_dict.get("type") == "investigate":
                target = action_dict.get("target")
                result = action_dict.get("result")
                # Cop/Consigliere logic typically updates the player's memory. 
                # We also store it in environment logs.
                self.state.log_hidden(
                    actor, f"Investigation result on {target}: {result}"
                )
                self.state.night_action_results[actor] = action_dict

        if deaths:
            # Alphabetical or by order of kills
            self.state.log_message(
                "system",
                f"The sun rises. The following were found dead: {', '.join(sorted(deaths))}."
            )
        else:
            self.state.log_message("system", "The sun rises. Miraculously, nobody died last night!")

    def _transition_to_day(self):
        """Moves the game into DAY_DISCUSSION, resetting relevant flags and re-initializing speaker queues."""
        self.state.log_hidden("system", "Transitioning to Day phase.")
        # Clear roleblock statuses, etc.
        for p in self.state.players:
            p.reset_night_state()

        # Switch to day
        self.state.phase = GamePhase.DAY_DISCUSSION
        self.state.day_count += 1
        self.state.reset_day_phase_state()

        # Start a fresh speaking queue
        self._start_new_discussion_round()
        self.state.log_message("system", f"Day {self.state.day_count} begins. Discuss and vote!")

    def _start_new_discussion_round(self):
        """Initializes or re-initializes the round-robin talk queue for the day discussion phase."""
        self._speaker_queue.clear()
        self._question_queue.clear()
        self._turns_taken_this_round.clear()
        self._consecutive_passes = 0
        self.state.turn_context = None
        self.state.turn_number_in_phase = 0

        alive_names = sorted(self.state.alive_players)
        # If config demands Cop speak first
        if self.cop_speaks_first:
            for name in alive_names:
                pl = self.state.get_player(name)
                if pl and isinstance(pl.role, Cop):
                    alive_names.remove(name)
                    alive_names.insert(0, name)
                    self.state.log_hidden("system", f"Cop ({name}) will speak first today.")
                    break

        self._speaker_queue.extend(alive_names)
        # Force the environment to choose the first speaker
        self.advance_turn()

    def _check_discussion_end(self) -> bool:
        """
        Checks if we must end DAY_DISCUSSION:
          - Everyone passes in a row
          - An accusation is made
          - The day discussion round is otherwise complete (all spoke, queue empty)
          - (Optional) A max turn or time-based limit
        """
        # 1. Everyone passes consecutively
        if self._consecutive_passes >= len(self.state.alive_players):
            self.state.log_hidden("system", "All players have consecutively passed. Discussion ending.")
            return True

        # 2. If the queue is empty and every living player has spoken at least once
        if (not self._speaker_queue and not self._question_queue 
                and len(self._turns_taken_this_round) >= len(self.state.alive_players)):
            self.state.log_hidden("system", "Discussion round ended: queue empty, everyone spoke.")
            return True

        # 3. If someone is on trial already (accusation triggered)
        if self.state.player_on_trial:
            self.state.log_hidden("system", f"Discussion ended: {self.state.player_on_trial} was put on trial.")
            return True

        return False

    def _transition_to_voting(self):
        """
        Day discussion → Voting on the accused (or skipping to night if no accusations).
        """
        if not self.state.player_on_trial:
            self.state.log_message("system", "No one was put on trial today.")
            self._transition_to_night()
            return

        self.state.log_message("system", f"{self.state.player_on_trial} is on trial!")
        self.state.votes_for_lynch.clear()

        if self.lynch_defense_enabled:
            self.state.phase = GamePhase.DEFENSE
            self.state.current_player_turn = self.state.player_on_trial
            self.state.log_message(
                "system",
                f"{self.state.player_on_trial}, you may speak in your defense."
            )
        else:
            # Skip defense and go directly to final vote
            self._transition_to_final_vote()

    def _run_defense(self):
        """
        A placeholder hook for the defense phase. 
        The simulation typically calls process_player_action(...) so the accused can make a statement.
        """
        self.state.log_hidden("system", f"Defense phase for {self.state.player_on_trial}.")

    def _transition_to_final_vote(self):
        """
        Moves from DEFENSE → FINAL_VOTE. 
        All alive players can vote guilty/innocent simultaneously or in a loop if you prefer.
        """
        self.state.phase = GamePhase.FINAL_VOTE
        self.state.current_player_turn = None
        self.state.votes_for_lynch.clear()
        self.state.log_message(
            "system",
            f"Final voting begins for {self.state.player_on_trial}. Vote GUILTY or INNOCENT."
        )

    def _resolve_lynch(self):
        """
        After the final vote, count how many guilty vs. innocent votes. 
        Majority (strictly >= half+1) => lynch. Otherwise, no lynch.
        """
        if not self.state.player_on_trial:
            self.state.log_hidden("system", "No player on trial, skipping lynch resolution.")
            return

        votes = self.state.votes_for_lynch
        guilty = sum(1 for is_guilty in votes.values() if is_guilty)
        innocent = len(votes) - guilty
        total_alive = len(self.state.alive_players)
        needed_for_lynch = (total_alive // 2) + 1

        self.state.log_message(
            "system",
            f"Vote Results for {self.state.player_on_trial}: "
            f"Guilty={guilty}, Innocent={innocent}. Need {needed_for_lynch} to lynch."
        )
        self.state.log_hidden("system", f"Final Votes: {votes}")

        if guilty >= needed_for_lynch:
            self.state.log_message("system", f"The town has decided to lynch {self.state.player_on_trial}!")
            self.state.kill_player(self.state.player_on_trial, reason="lynched")
        else:
            self.state.log_message("system", f"The vote is inconclusive, sparing {self.state.player_on_trial}.")

        self.state.player_on_trial = None

    def _transition_to_night(self):
        """
        Resets day state and transitions to NIGHT, unless the game has ended.
        Typically called after lynch resolution or if no trial occurred.
        """
        self.state.log_hidden("system", "Transitioning to Night phase.")
        if self.state.player_on_trial and self.state.phase != GamePhase.NIGHT:
            # If for some reason we haven't resolved the lynch yet, do it now
            self._resolve_lynch()

        if self.state.check_game_end():
            return  # If game ended from a lynch, stop here

        self.state.phase = GamePhase.NIGHT
        self.state.reset_night_phase_state()
        self.state.current_player_turn = None
        self.state.log_message("system", "Night falls. Mafia members, choose your targets...")

    def apply_rewards(self):
        """
        Optional: If you have a reward system, call it here to store or return
        partial or final rewards for each player/agent.
        """
        rewards = compute_rewards(self.state)
        self.state.log_hidden("system", f"Computed rewards (not saved): {rewards}")
        # Optionally store them in the GameState or return them

    # ----------------------------------------------------------------
    # Day-Phase Action Helpers
    # ----------------------------------------------------------------

    def _process_day_discussion_action(
        self, 
        player: Player, 
        action_type: str, 
        target: Optional[str], 
        content: Optional[str]
    ) -> bool:
        """
        Handle actions that can occur specifically in the DAY_DISCUSSION phase.
        Returns True if valid, False otherwise.
        """
        # Reset consecutive passes only if the action is not a "pass"
        if action_type == "pass":
            self._consecutive_passes += 1
            self.state.log_message(player.name, f"{player.name} passes.")
            # Mark that the player has taken a turn
            self._turns_taken_this_round.add(player.name)
            return True
        else:
            # They did something, so reset the pass counter
            self._consecutive_passes = 0

        # Accuse
        if action_type == "accuse" and target:
            if self.state.player_on_trial:
                self.state.log_hidden(player.name, "Cannot accuse; someone is already on trial.")
                return False
            success = player.accuse(target, self.state)
            if success:
                self.state.player_on_trial = target
            self._turns_taken_this_round.add(player.name)
            return success

        # Vote (during discussion, not final vote)
        elif action_type == "vote" and target:
            success = player.vote_for(target, self.state)
            self._turns_taken_this_round.add(player.name)
            return success

        # Question
        elif action_type == "question" and target and content:
            # Possibly limit # of questions per day, per target
            times_asked = player.questions_asked_today.get(target, 0)
            if times_asked >= 1:
                self.state.log_hidden(player.name, f"Question limit reached for {target}.")
                return False
            success = player.question(target, content, self.state)
            if success:
                player.questions_asked_today[target] = times_asked + 1
                # Add the Q&A flow to the question queue
                self._question_queue.append((player.name, target))
                # Then the questioner is scheduled to respond
                self._question_queue.append((player.name, player.name))
            self._turns_taken_this_round.add(player.name)
            return success

        # Predict role
        elif action_type == "predict" and target and content:
            success = player.predict_role(target, content, self.state)
            self._turns_taken_this_round.add(player.name)
            return success

        # Whisper
        elif action_type == "whisper" and target and content:
            success = player.whisper(target, content, self.state)
            self._turns_taken_this_round.add(player.name)
            return success

        # Generic talk
        elif action_type == "speak":
            if content:
                self.state.log_message(player.name, content)
                self._turns_taken_this_round.add(player.name)
                return True
            else:
                self.state.log_hidden(player.name, "Tried to speak but no content was provided.")
                return False

        # If none of the above matched, treat as invalid or a default "speak"
        if content:
            self.state.log_message(player.name, content)
            self._turns_taken_this_round.add(player.name)
            return True

        self.state.log_hidden(player.name, f"Invalid or unrecognized day action: {action_type}")
        return False

    def _process_voting_phase_action(
        self,
        player: Player,
        action_type: str,
        target: Optional[str],
        content: Optional[str]
    ) -> bool:
        """
        Handle standard voting phase (pre-defense or a simpler immediate-voting system).
        If you prefer all final votes to happen in FINAL_VOTE, you can keep this minimal.
        """
        if action_type == "vote" and target == self.state.player_on_trial:
            # If the environment merges "voting" and "final vote," you could do a direct guilty/innocent.
            # Otherwise, you might track 'vote_for_lynch' in the state, or do a simpler approach.
            player.vote_for(target, self.state)
            self.state.log_message(player.name, f"votes to lynch {target} in the standard voting phase.")
            return True

        # You can add logic for 'skip' or 'abstain' as well:
        elif action_type == "skip":
            self.state.log_message(player.name, f"{player.name} decides not to vote right now.")
            return True

        self.state.log_hidden(player.name, f"Invalid or mismatched action {action_type} in VOTING phase.")
        return False

    def _process_final_vote_action(self, player: Player, action: Dict[str, Any]) -> bool:
        """
        In FINAL_VOTE phase, each player declares GUILTY or INNOCENT (or possibly abstains).
        action might look like {"action": "vote", "vote_type": "final_guilty"}
        """
        action_type = action.get("action")
        vote_type_str = action.get("vote_type", "").lower()

        # Must be a "vote" action
        if action_type != "vote":
            self.state.log_hidden(player.name, f"Expected a vote action in FINAL_VOTE, got {action_type}.")
            return False

        if vote_type_str == "final_guilty":
            self.state.votes_for_lynch[player.name] = True
            self.state.log_message(
                player.name,
                f"votes GUILTY on {self.state.player_on_trial}."
            )
            return True
        elif vote_type_str == "final_innocent":
            self.state.votes_for_lynch[player.name] = False
            self.state.log_message(
                player.name,
                f"votes INNOCENT on {self.state.player_on_trial}."
            )
            return True
        elif vote_type_str == "abstain":
            self.state.log_message(player.name, f"abstains from voting.")
            return True
        else:
            self.state.log_hidden(
                player.name,
                f"Invalid final vote type: {vote_type_str} (expected 'final_guilty' or 'final_innocent')."
            )
            return False

    # ----------------------------------------------------------------
    # Night Action Validation
    # ----------------------------------------------------------------

    def _validate_night_action(self, player: Player, action_dict: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Optional: Enforces certain constraints on night actions:
          - Godfather cannot kill themselves or a fellow Mafia
          - Cop cannot investigate themselves
          - Roleblocker cannot block themselves
          - ...
        Return the action_dict if valid, or None if invalid.
        """
        if not action_dict:
            return None

        action_type = action_dict.get("type")
        target = action_dict.get("target")

        # Basic checks: must have a target
        if not target:
            self.state.log_hidden(player.name, "No target specified for night action.")
            return None

        # Cop cannot investigate self
        if action_type == "investigate" and target == player.name:
            self.state.log_hidden(player.name, "Cop tried to investigate themselves; invalid.")
            return None

        # Godfather can't kill themselves or mafia
        if action_type == "kill" and isinstance(player.role, Godfather):
            target_p = self.state.get_player(target)
            if target_p:
                if target_p.faction == Faction.MAFIA or target_p.name == player.name:
                    self.state.log_hidden(
                        player.name,
                        "Godfather tried to kill themselves or a fellow Mafia, invalid action."
                    )
                    return None

        # Roleblocker cannot block themselves (if you have a RoleBlocker role)
        if action_type == "roleblock" and isinstance(player.role, RoleBlocker):
            if target == player.name:
                self.state.log_hidden(player.name, "RoleBlocker tried to block themselves, invalid.")
                return None

        return action_dict
