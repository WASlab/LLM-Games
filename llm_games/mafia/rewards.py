# mafia/rewards.py
from typing import Dict
from llm_games.mafia.enums import Faction


def assign_endgame_rewards(game_state) -> Dict[str, float]:
    """
    Assign final rewards to agents based on game outcome.
    Town agents get +1 for town win, -1 otherwise. Same for mafia.
    """
    rewards = {}
    for player in game_state.players:
        if player.faction.value == game_state.winner:
            rewards[player.name] = 1.0
        else:
            rewards[player.name] = -1.0
    return rewards


def assign_predict_role_reward(predicted: str, actual: str) -> float:
    return 0.5 if predicted == actual else -0.25


def assign_vote_reward(voter, target, game_state) -> float:
    """
    +1 if town correctly votes out mafia
    -1 if town votes town
    +0.5 if mafia avoids being voted
    """
    if not game_state.is_alive(target):  # Lynched
        if voter.faction == Faction.TOWN:
            if game_state.get_player(target).faction == Faction.MAFIA:
                return 1.0
            else:
                return -1.0
        elif voter.faction == Faction.MAFIA:
            if game_state.get_player(target).faction == Faction.MAFIA:
                return -1.0
            else:
                return 0.5
    return 0.0


def assign_speaking_reward(agent_name: str, token_used: int) -> float:
    """
    Optional: Reward for verbosity, or penalize excess verbosity.
    For now, neutral. Could be tuned.
    """
    return 0.0


def assign_question_reward(asker, target, game_state) -> float:
    """
    +0.2 for engaging others; could scale if target is mafia and asker is town
    """
    if asker.faction == Faction.TOWN and target.faction == Faction.MAFIA:
        return 0.4
    return 0.2
