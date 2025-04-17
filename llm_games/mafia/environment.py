import random
from collections import deque
from typing import Dict, List, Optional, Any, Tuple, Set
import re

# Core project imports (ensure they match your directory structure)
from llm_games.mafia.game_state import GameState, GameMessage
from llm_games.mafia.player import Player
from llm_games.mafia.enums import GamePhase, Faction, VoteType
from llm_games.mafia.mechanics.roles import Cop, Godfather, RoleBlocker, Doctor

# ----------------------------------------------------------------
# Tag parsing helper  ‑‑ now also supports <predict>
# ----------------------------------------------------------------
def parse_speak_tags(content: str) -> Dict[str, List[str]]:
    """
    Parses embedded action tags (case‑insensitive).

    Supported examples
    ------------------
    <accuse>Alice</accuse>
    <question>Alice, Bob</question>
    <claim>Doctor</claim>
    <predict>Charlie:Cop</predict>   # optional – mostly used at night
    """
    tag_patterns = {
        "accuse":   r"<\s*accuse\s*>(.*?)<\s*/\s*accuse\s*>",
        "question": r"<\s*question\s*>(.*?)<\s*/\s*question\s*>",
        "claim":    r"<\s*claim\s*>(.*?)<\s*/\s*claim\s*>",
        "predict":  r"<\s*predict\s*>(.*?)<\s*/\s*predict\s*>",
    }
    extracted: Dict[str, List[str]] = {}
    for tag, pattern in tag_patterns.items():
        matches = re.findall(pattern, content, flags=re.IGNORECASE | re.DOTALL)
        cleaned = [m.strip() for m in matches if m and m.strip()]
        if cleaned:
            extracted[tag] = cleaned
    return extracted



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

    Added features:
      - Robust Q&A: question tags in speech push players to front of queue,
        limited to 3 rounds/day, one question per target.
      - Talk tags are parsed but only Q&A is actioned here; other tags
        (accuse/claim) can be implemented similarly.
    """

    def __init__(self, players: List[Player], config: Dict[str, Any]):
        self.config = config
        self.state = GameState(players=players, game_config=config)
        self.state.initialize()
        self.token_tracker = TokenTracker()

        # Config flags
        self.lynch_defense_enabled: bool = self.config.get("lynch_defense_enabled", True)
        self.cop_speaks_first: bool = self.config.get("cop_speaks_first", False)

        # Day-phase tracking
        self._speaker_queue: deque[str] = deque()
        self._question_queue: deque[Tuple[str, str]] = deque()
        self._turns_taken_this_round: Set[str] = set()
        self._consecutive_passes: int = 0

        # Q&A limits per day
        self._question_rounds_taken: Dict[str, int] = {}

    # ----------------------------------------------------------------
    # Public Methods for Simulation Loop
    # ----------------------------------------------------------------

    def step_phase(self) -> bool:
        if self.state.game_over:
            return True
        current_phase = self.state.phase

        if current_phase == GamePhase.NIGHT:
            self._resolve_night()
            self._transition_to_day()
        elif current_phase == GamePhase.DAY_DISCUSSION:
            if self._check_discussion_end():
                self._transition_to_voting()
        elif current_phase == GamePhase.VOTING:
            pass
        elif current_phase == GamePhase.DEFENSE:
            self._run_defense()
            self._transition_to_final_vote()
        elif current_phase == GamePhase.FINAL_VOTE:
            self._resolve_lynch()
            self._transition_to_night()

        return self.state.check_game_end()

    def get_current_player_name(self) -> Optional[str]:
        return self.state.current_player_turn

    def get_observation(self, player_name: str) -> Dict[str, Any]:
        return self.state.get_player_observation(player_name)

    def process_player_action(self, player_name: str, action: Dict[str, Any]) -> bool:
        """Single entry‑point for *every* action an agent can take."""
        player = self.state.get_player(player_name)
        if not player or not player.alive:
            self.state.log_hidden(player_name, f"Ignored action {action}; player dead/invalid.")
            return False

        # Turn‑order enforcement (day only)
        if self.state.phase == GamePhase.DAY_DISCUSSION and self.state.current_player_turn != player_name:
            self.state.log_hidden(player_name, f"Out‑of‑turn action {action}.")
            return False

        self.state.log_hidden(player_name, f"Received action: {action}")
        action_type   = action.get("action")
        target        = action.get("target")
        content       = action.get("content")
        predicted_str = action.get("predicted_role") or action.get("prediction")

        success = False

        # ------------------------------  NIGHT  ------------------------------
        if self.state.phase == GamePhase.NIGHT:
            # meta‑action: <predict>
            if action_type == "predict" and target and predicted_str:
                success = player.predict_role(target, predicted_str, self.state)
                # keep going – they may also do their normal role action

            if player.can_act_at_night() and action_type != "predict":
                intended = player.perform_night_action(self.state)
                intended = self._validate_night_action(player, intended)
                if intended:
                    self.state.register_night_action(player_name, intended)
                success = True
            else:
                success = success or False  # keep whatever predict_result said

        # ------------------------  DAY DISCUSSION  ---------------------------
        elif self.state.phase == GamePhase.DAY_DISCUSSION:
            if action_type == "speak" and content:
                tags = parse_speak_tags(content)

                # ---------- Q & A (comma‑separated targets, 3 rounds max) ----------
                raw_questions = tags.get("question", [])
                question_targets: List[str] = []
                for q in raw_questions:
                    question_targets.extend([p.strip() for p in q.split(",") if p.strip()])

                if question_targets:
                    rounds_used = self._question_rounds_taken.get(player_name, 0)
                    if rounds_used < 3:
                        new_targets = [
                            tgt for tgt in question_targets
                            if tgt not in player.questions_asked_today
                        ]
                        if new_targets:
                            self._question_rounds_taken[player_name] = rounds_used + 1
                            for tgt in new_targets:
                                player.questions_asked_today[tgt] = 1

                            order = new_targets + [player_name]          # all targets first, asker last
                            for whom in reversed(order):
                                self._question_queue.appendleft((player_name, whom))

                            self.state.log_hidden(player_name, f"Queued question round for: {new_targets}")
                    else:
                        self.state.log_hidden(player_name, "Question round limit reached (3).")

                # log the speech itself
                self.state.log_message(player.name, content)
                self._turns_taken_this_round.add(player.name)
                success = True
                if not self.state.player_on_trial:
                    self.advance_turn()

            else:
                success = self._process_day_discussion_action(player, action_type, target, content)
                if success and not self.state.player_on_trial:
                    self.advance_turn()

        # ---------------- VOTING / DEFENSE / FINAL VOTE ----------------------
        elif self.state.phase == GamePhase.VOTING:
            success = self._process_voting_phase_action(player, action_type, target, content)

        elif self.state.phase == GamePhase.DEFENSE:
            if player_name == self.state.player_on_trial:
                msg = f"(Defense) {content}" if content else "(Defense) [No statement]"
                self.state.log_message(player_name, msg)
                success = True
            else:
                self.state.log_hidden(player_name, "Ignored defense action – not on trial.")

        elif self.state.phase == GamePhase.FINAL_VOTE:
            success = self._process_final_vote_action(player, action)

        if not success:
            self.state.log_hidden(player_name, f"Action {action} failed or was invalid.")
        return success

    def advance_turn(self):
        if self.state.phase != GamePhase.DAY_DISCUSSION:
            self.state.current_player_turn = None
            return
        # Prioritize any question queue
        if self._question_queue:
            qer, qee = self._question_queue.popleft()
            self.state.current_player_turn = qee
            self.state.turn_context = {"answering_question_from": qer}
            return
        # Otherwise normal speaker queue
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
        """Resolves all night actions (roleblock, protect, kill, investigate)."""
        self.state.log_message("system", "Night ends. Resolving all night actions...")
        self.state.night_action_results.clear()
        submitted_actions = self.state.night_actions_submitted

        roleblocked_players: Set[str] = set()
        blackmailed_players: Set[str] = set()

        for actor, action_dict in submitted_actions.items():
            if not self.state.is_alive(actor):
                continue
            if action_dict.get("type") == "roleblock":
                target = action_dict.get("target")
                if target and self.state.is_alive(target):
                    roleblocked_players.add(target)
                    self.state.log_hidden(actor, f"Roleblocked {target} for the night.")
            elif action_dict.get("type") == "blackmail":
                target = action_dict.get("target")
                if target and self.state.is_alive(target):
                    blackmailed_players.add(target)
                    self.state.log_hidden(actor, f"Blackmailed {target} for the day.")

        for blocked in roleblocked_players:
            p = self.state.get_player(blocked)
            if p:
                p.is_roleblocked = True

        for bm in blackmailed_players:
            p = self.state.get_player(bm)
            if p:
                p.can_speak_today = False

        protected: Dict[str, str] = {}
        for actor, action_dict in submitted_actions.items():
            if actor in roleblocked_players:
                continue
            if not self.state.is_alive(actor):
                continue
            if action_dict.get("type") == "protect":
                target = action_dict.get("target")
                if target and self.state.is_alive(target):
                    if target not in protected:
                        protected[target] = actor
                        target_p = self.state.get_player(target)
                        if target_p:
                            target_p.protected_by = actor
                        self.state.log_hidden(actor, f"Protected {target} this night.")

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
        for killer, target in kills_attempted:
            if target not in protected:
                successful_kills.add(target)
                self.state.log_hidden(killer, f"Kill on {target} succeeded.")
            else:
                doc = protected[target]
                self.state.log_hidden(killer, f"Kill on {target} failed (protected by {doc}).")
                self.state.log_hidden(doc, f"You successfully protected {target} from a kill.")

        deaths = []
        for victim in successful_kills:
            if self.state.is_alive(victim):
                self.state.kill_player(victim, reason="killed during night")
                deaths.append(victim)

        for actor, action_dict in submitted_actions.items():
            if actor in roleblocked_players:
                continue
            if not self.state.is_alive(actor):
                continue
            if action_dict.get("type") == "investigate":
                target = action_dict.get("target")
                result = action_dict.get("result")
                self.state.log_hidden(actor, f"Investigation result on {target}: {result}")
                self.state.night_action_results[actor] = action_dict

        if deaths:
            self.state.log_message("system", f"The sun rises. The following were found dead: {', '.join(sorted(deaths))}.")
        else:
            self.state.log_message("system", "The sun rises. Miraculously, nobody died last night!")

    def _transition_to_day(self):
        """Transitions the game to the DAY_DISCUSSION phase."""
        self.state.log_hidden("system", "Transitioning to Day phase.")
        for p in self.state.players:
            p.reset_night_state()
        self.state.phase = GamePhase.DAY_DISCUSSION
        self.state.day_count += 1
        self.state.reset_day_phase_state()
        self._start_new_discussion_round()
        self.state.log_message("system", f"Day {self.state.day_count} begins. Discuss and vote!")

    def _start_new_discussion_round(self):
        """Initializes the round-robin speaker queue for DAY_DISCUSSION."""
        self._speaker_queue.clear()
        self._question_queue.clear()
        self._turns_taken_this_round.clear()
        self._consecutive_passes = 0
        self.state.turn_context = None
        self.state.turn_number_in_phase = 0

        alive_names = sorted(self.state.alive_players)
        if self.cop_speaks_first:
            for name in alive_names:
                pl = self.state.get_player(name)
                if pl and isinstance(pl.role, Cop):
                    alive_names.remove(name)
                    alive_names.insert(0, name)
                    self.state.log_hidden("system", f"Cop ({name}) will speak first today.")
                    break

        self._speaker_queue.extend(alive_names)
        self.advance_turn()

    def _check_discussion_end(self) -> bool:
        alive_count = len(self.state.alive_players)
        min_turns = self.config.get("min_discussion_turns", 2)
        if self.state.day_count == 0:
            min_turns = 1

        player_turn_counts = {p: 0 for p in self.state.alive_players}
        for entry in self.state.hidden_log:
            if entry.get("phase") == GamePhase.DAY_DISCUSSION.name and entry.get("actor") in player_turn_counts:
                player_turn_counts[entry["actor"]] += 1

        self.state.log_hidden("system", f"Discussion turn counts: {player_turn_counts}")

        if all(count >= min_turns for count in player_turn_counts.values()):
            self.state.log_hidden("system", f"All players completed {min_turns} discussion turns. Ending discussion.")
            return True

        if self._consecutive_passes >= alive_count:
            self.state.log_hidden("system", "All players passed consecutively. Ending discussion.")
            return True

        return False

    def _transition_to_voting(self):
        """
        Transitions from DAY_DISCUSSION to Voting (or Defense if enabled) based on accusations.
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
            self.state.log_message("system", f"{self.state.player_on_trial}, you may speak in your defense.")
        else:
            self._transition_to_final_vote()

    def _run_defense(self):
        """Placeholder for defense phase processing."""
        self.state.log_hidden("system", f"Defense phase for {self.state.player_on_trial}.")

    def _transition_to_final_vote(self):
        """Transitions from Defense to FINAL_VOTE."""
        self.state.phase = GamePhase.FINAL_VOTE
        self.state.current_player_turn = None
        self.state.votes_for_lynch.clear()
        self.state.log_message("system", f"Final voting begins for {self.state.player_on_trial}. Vote GUILTY or INNOCENT.")

    def _resolve_lynch(self):
        """
        Resolves the final vote and determines if the player on trial is lynched.
        """
        if not self.state.player_on_trial:
            self.state.log_hidden("system", "No player on trial, skipping lynch resolution.")
            return

        votes = self.state.votes_for_lynch
        guilty = sum(1 for is_guilty in votes.values() if is_guilty)
        innocent = len(votes) - guilty
        total_alive = len(self.state.alive_players)
        needed_for_lynch = (total_alive // 2) + 1

        self.state.log_message("system",
            f"Vote Results for {self.state.player_on_trial}: Guilty={guilty}, Innocent={innocent}. Need {needed_for_lynch} to lynch.")
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
        """
        self.state.log_hidden("system", "Transitioning to Night phase.")
        if self.state.player_on_trial and self.state.phase != GamePhase.NIGHT:
            self._resolve_lynch()
        if self.state.check_game_end():
            return
        self.state.phase = GamePhase.NIGHT
        self.state.reset_night_phase_state()
        self.state.current_player_turn = None
        self.state.log_message("system", "Night falls. Mafia members, choose your targets...")

    def apply_rewards(self):
        """Optional: Apply rewards using a reward system if implemented."""
        rewards = compute_rewards(self.state)
        self.state.log_hidden("system", f"Computed rewards (not saved): {rewards}")

    # ----------------------------------------------------------------
    # Day-Phase Action Helpers
    # ----------------------------------------------------------------

    def _process_day_discussion_action(self, player: Player, action_type: str, target: Optional[str], content: Optional[str]) -> bool:
        """
        Processes actions during DAY_DISCUSSION.
        This handles both explicit actions (like 'accuse', 'vote') and 'speak' actions with embedded tags.
        """
        if action_type == "pass":
            self._consecutive_passes += 1
            self.state.log_message(player.name, f"{player.name} passes.")
            self._turns_taken_this_round.add(player.name)
            return True
        elif action_type == "accuse" and target:
            if self.state.day_count == 0:
                self.state.log_hidden(player.name, "Accusations are not allowed on Day 0.")
                return False
            success = player.accuse(target, self.state)
            if success:
                self.state.player_on_trial = target
            self._turns_taken_this_round.add(player.name)
            return success
        else:
            self._consecutive_passes = 0

        # Handle explicit accuse again (if sent separately)
        if action_type == "accuse" and target:
            if self.state.player_on_trial:
                self.state.log_hidden(player.name, "Cannot accuse; someone is already on trial.")
                return False
            success = player.accuse(target, self.state)
            if success:
                self.state.player_on_trial = target
            self._turns_taken_this_round.add(player.name)
            return success

        elif action_type == "vote" and target:
            success = player.vote_for(target, self.state)
            self._turns_taken_this_round.add(player.name)
            return success

        elif action_type == "question" and target and content:
            times_asked = player.questions_asked_today.get(target, 0)
            if times_asked >= 1:
                self.state.log_hidden(player.name, f"Question limit reached for {target}.")
                return False
            success = player.question(target, content, self.state)
            if success:
                player.questions_asked_today[target] = times_asked + 1
                self._question_queue.append((player.name, target))
                self._question_queue.append((player.name, player.name))
            self._turns_taken_this_round.add(player.name)
            return success

        elif action_type == "predict" and target and content:
            success = player.predict_role(target, content, self.state)
            self._turns_taken_this_round.add(player.name)
            return success

        elif action_type == "whisper" and target and content:
            success = player.whisper(target, content, self.state)
            self._turns_taken_this_round.add(player.name)
            return success

        elif action_type == "speak":
            if content:
                # Before logging the speak message, process nested tags.
                nested_actions = parse_speak_tags(content)
                if nested_actions:
                    if "accuse" in nested_actions and not self.state.player_on_trial:
                        accuse_target = nested_actions["accuse"][0]
                        if player.accuse(accuse_target, self.state):
                            self.state.player_on_trial = accuse_target
                    if "question" in nested_actions:
                        for q in nested_actions["question"]:
                            if player.questions_asked_today.get(q, 0) < 1:
                                if player.question(q, "Question embedded in speak action", self.state):
                                    player.questions_asked_today[q] = player.questions_asked_today.get(q, 0) + 1
                                    self._question_queue.append((player.name, q))
                                    self._question_queue.append((player.name, player.name))
                    if "claim" in nested_actions:
                        for claim in nested_actions["claim"]:
                            player.log_hidden(self.state, f"Claimed role: {claim}")
                clean_content = strip_tags(content)
                self.state.log_message(player.name, clean_content)
                self._turns_taken_this_round.add(player.name)
                return True
            else:
                self.state.log_hidden(player.name, "Tried to speak but no content was provided.")
                return False

        if content:
            self.state.log_message(player.name, content)
            self._turns_taken_this_round.add(player.name)
            return True

        self.state.log_hidden(player.name, f"Invalid or unrecognized day action: {action_type}")
        return False

    def _process_voting_phase_action(self, player: Player, action_type: str, target: Optional[str], content: Optional[str]) -> bool:
        if action_type == "vote" and target == self.state.player_on_trial:
            player.vote_for(target, self.state)
            self.state.log_message(player.name, f"votes to lynch {target} in the standard voting phase.")
            return True
        elif action_type == "skip":
            self.state.log_message(player.name, f"{player.name} decides not to vote right now.")
            return True
        self.state.log_hidden(player.name, f"Invalid or mismatched action {action_type} in VOTING phase.")
        return False

    def _process_final_vote_action(self, player: Player, action: Dict[str, Any]) -> bool:
        action_type = action.get("action")
        vote_type_str = action.get("vote_type", "").lower()
        if action_type != "vote":
            self.state.log_hidden(player.name, f"Expected a vote action in FINAL_VOTE, got {action_type}.")
            return False
        if vote_type_str == "final_guilty":
            self.state.votes_for_lynch[player.name] = True
            self.state.log_message(player.name, f"votes GUILTY on {self.state.player_on_trial}.")
            return True
        elif vote_type_str == "final_innocent":
            self.state.votes_for_lynch[player.name] = False
            self.state.log_message(player.name, f"votes INNOCENT on {self.state.player_on_trial}.")
            return True
        elif vote_type_str == "abstain":
            self.state.log_message(player.name, f"abstains from voting.")
            return True
        else:
            self.state.log_hidden(player.name, f"Invalid final vote type: {vote_type_str} (expected 'final_guilty' or 'final_innocent').")
            return False

    def _validate_night_action(self, player: Player, action_dict: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not action_dict:
            return None
        action_type = action_dict.get("type")
        target = action_dict.get("target")
        if not target:
            self.state.log_hidden(player.name, "No target specified for night action.")
            return None
        if action_type == "investigate" and target == player.name:
            self.state.log_hidden(player.name, "Cop tried to investigate themselves; invalid.")
            return None
        if action_type == "kill" and isinstance(player.role, Godfather):
            target_p = self.state.get_player(target)
            if target_p:
                if target_p.faction == Faction.MAFIA or target_p.name == player.name:
                    self.state.log_hidden(player.name, "Godfather tried to kill themselves or a fellow Mafia, invalid action.")
                    return None
        if action_type == "roleblock" and isinstance(player.role, RoleBlocker):
            if target == player.name:
                self.state.log_hidden(player.name, "RoleBlocker tried to block themselves, invalid.")
                return None
        return action_dict

    # ----------------------------------------------------------------
    # Phase Tracking, Logging, and Observation
    # ----------------------------------------------------------------

    def get_game_summary(self) -> Dict[str, Any]:
        summary = {
            "game_id": self.state.game_id,
            "phase": self.state.phase.name,
            "day_count": self.state.day_count,
            "game_over": self.state.game_over,
            "winner": self.state.winner.value if self.state.winner else None,
            "alive_players": sorted(list(self.state.alive_players)),
            "dead_players": sorted(list(self.state.dead_players)),
            "final_player_roles": dict(self.state.final_player_roles),
            "messages_count": len(self.state.messages),
            "hidden_log_count": len(self.state.hidden_log),
            "phase_history": self.state.phase_history,
        }
        return summary

    def get_player_observation(self, player_name: str) -> Dict[str, Any]:
        """
        Generates an observation for a player, including:
          - Public messages,
          - Player list with status tags,
          - Private memory,
          - Phase details and turn info,
          - Mafia members list for Mafia players.
        """
        player = self.state.get_player(player_name)
        if not player or not player.alive:
            return {
                "game_id": self.state.game_id,
                "player_name": player_name,
                "alive": False,
                "message": "You are no longer in the game."
            }
        visible_messages: List[str] = []
        for msg in self.state.messages:
            is_recip_private = (msg.recipients is not None and player_name in msg.recipients)
            is_sender_private = (msg.sender == player_name and msg.recipients is not None)
            if (msg.recipients is None) or is_recip_private or is_sender_private:
                if msg.msg_type == "whisper":
                    if is_sender_private:
                        visible_messages.append(f"(Whisper to {msg.recipients[0]}) {msg.content}")
                    elif is_recip_private:
                        visible_messages.append(f"(Whisper from {msg.sender}) {msg.content}")
                    else:
                        visible_messages.append(f"{msg.sender}: {msg.content}")
                else:
                    visible_messages.append(f"{msg.sender}: {msg.content}")

        # Build player list with status tags.
        player_list_str = []
        all_players = list(set(list(self.state.alive_players) + list(self.state.dead_players)))
        on_trial = self.state.player_on_trial
        for pname in sorted(all_players):
            tags = []
            if pname in self.state.dead_players:
                tags.append("DEAD")
            if pname == on_trial:
                tags.append("On Trial")
            # For Mafia players, reveal their faction if the observer is Mafia.
            observer = self.state.get_player(player_name)
            target_player = self.state.get_player(pname)
            if observer and target_player:
                if observer.faction == Faction.MAFIA and target_player.faction == Faction.MAFIA:
                    tags.append("Mafia")
            status = f" [{' '.join(tags)}]" if tags else ""
            player_list_str.append(f"{pname}{status}")

        mafia_members = []
        if player.faction == Faction.MAFIA:
            mafia_members = [p.name for p in self.state.players if p.alive and p.faction == Faction.MAFIA]

        obs = {
            "game_id": self.state.game_id,
            "player_name": player.name,
            "role": player.role.name,
            "role_description": player.role.get_role_description(),
            "faction": player.faction.value,
            "phase": self.state.phase.name,
            "day": self.state.day_count,
            "turn": self.state.turn_number_in_phase,
            "is_current_turn": (self.state.current_player_turn == player.name),
            "alive_players": sorted(list(self.state.alive_players)),
            "dead_players": sorted(list(self.state.dead_players)),
            "messages": visible_messages[-20:],
            "can_speak": player.can_speak(),
            "can_act_tonight": (player.can_act_at_night() and self.state.phase == GamePhase.NIGHT),
            "player_on_trial": on_trial,
            "votes_for_accusation": dict(self.state.votes_for_accusation),
            "accusation_counts": dict(self.state.accusation_counts),
            "memory": list(player.memory),
            "is_roleblocked": player.is_roleblocked,
            "protected_by": player.protected_by,
            "lynch_votes": {voter: val for voter, val in self.state.votes_for_lynch.items()},
            "mafia_members": mafia_members,
            "player_list": player_list_str,
            "current_player_turn": self.state.current_player_turn
        }
        return obs

    def record_phase_start(self):
        entry = {
            "phase": self.state.phase.name,
            "day": self.state.day_count,
            "turn_start": self.state.turn_number_in_phase,
            "timestamp": None  # Placeholder for actual time if desired
        }
        self.state.phase_history.append(entry)

    def record_phase_end(self):
        if self.state.phase_history:
            self.state.phase_history[-1]["turn_end"] = self.state.turn_number_in_phase
            self.state.phase_history[-1]["end_timestamp"] = None  # Placeholder for actual time

