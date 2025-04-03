# mafia/mechanics/voting.py
from typing import Dict, Optional
from mafia.enums import Phase
from mafia.game_state import GameState


def cast_vote(game_state: GameState, voter: str, target: str) -> None:
    """Player casts or changes vote for someone."""
    if game_state.phase != Phase.DAY or voter not in game_state.alive_players:
        return

    # Remove old vote if it exists
    if voter in game_state.voting_targets:
        prev_target = game_state.voting_targets[voter]
        if prev_target != target:
            game_state.messages.append(f"{voter} changed their vote from {prev_target} to {target}.")
    else:
        game_state.messages.append(f"{voter} has voted for {target}.")

    game_state.voting_targets[voter] = target
    check_accusation_threshold(game_state)


def retract_vote(game_state: GameState, voter: str) -> None:
    """Player retracts their vote."""
    if voter in game_state.voting_targets:
        prev = game_state.voting_targets.pop(voter)
        game_state.messages.append(f"{voter} retracted their vote on {prev}.")


def check_accusation_threshold(game_state: GameState, threshold: float = 0.5) -> None:
    """Automatically trigger accusation if a player reaches vote threshold."""
    vote_counts: Dict[str, int] = {}
    for target in game_state.voting_targets.values():
        vote_counts[target] = vote_counts.get(target, 0) + 1

    total_voters = len(game_state.alive_players)
    for target, count in vote_counts.items():
        if count / total_voters >= threshold and game_state.accused_player != target:
            game_state.accused_player = target
            game_state.messages.append(f"{target} has been accused and must now defend themselves.")


def confirm_lynch_vote(game_state: GameState, voter: str, confirm: bool) -> None:
    """Player confirms or denies the lynch after accusation."""
    if game_state.phase != Phase.DAY or not game_state.accused_player:
        return

    game_state.lynch_confirm_votes[voter] = confirm
    yes_votes = sum(1 for vote in game_state.lynch_confirm_votes.values() if vote)
    no_votes = sum(1 for vote in game_state.lynch_confirm_votes.values() if not vote)

    total_voters = len(game_state.alive_players)
    if yes_votes > total_voters // 2:
        game_state.messages.append(f"{game_state.accused_player} has been lynched by majority vote.")
        game_state.kill_player(game_state.accused_player)
        game_state.reset_votes()
    elif no_votes >= total_voters // 2:
        game_state.messages.append(f"{game_state.accused_player} has survived the vote.")
        game_state.reset_votes()


# --------------------------
# Whisper Mechanics
# --------------------------

def whisper(game_state: GameState, sender: str, recipient: str, message: str) -> None:
    """Send a whisper from one player to another. Hidden from all other agents."""
    if sender not in game_state.alive_players or recipient not in game_state.alive_players:
        return

    # Track hidden message to sender and recipient
    for player in game_state.players:
        if player.name in {sender, recipient}:
            player.log_hidden(game_state, f"[WHISPER] {sender} → {recipient}: {message}")
        else:
            player.log_hidden(game_state, f"[WHISPER] {sender} → {recipient}: <hidden>")

    # Log public metadata
    game_state.messages.append(f"{sender} whispered to {recipient}.")


# --------------------------
# Voting Visibility
# --------------------------

def get_vote_visibility(game_state: GameState) -> Dict[str, str]:
    """Return a dict of current votes (publicly visible for now)."""
    return {voter: target for voter, target in game_state.voting_targets.items()}
