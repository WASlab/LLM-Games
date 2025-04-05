# mafia/evaluation/analysis.py
from typing import List, Dict

def log_game_summary(game_state) -> Dict:
    """
    Logs key metrics and summary data from a completed game.
    Returns a structured dictionary with faction, winners, predictions, etc.
    """
    summary = {
        "game_id": game_state.game_id,
        "winner": game_state.winner,
        "day_count": game_state.day_count,
        "players": [],
        "predictions": [],
        "votes": [],
        "whispers": [],
        "questions": [],
        "accusations": [],
    }

    for player in game_state.players:
        summary["players"].append({
            "name": player.name,
            "role": player.role.name,
            "faction": player.faction.value,
            "alive": player.alive,
        })

        for target, role in player.predicted_roles.items():
            summary["predictions"].append({
                "predictor": player.name,
                "target": target,
                "predicted_role": role
            })

        if player.vote:
            summary["votes"].append({
                "voter": player.name,
                "voted_for": player.vote
            })

        for target, whisper_text in player.whispers_sent.items():
            summary["whispers"].append({
                "from": player.name,
                "to": target,
                "content": whisper_text
            })

        for target, count in player.questions_asked.items():
            summary["questions"].append({
                "asker": player.name,
                "target": target,
                "times": count
            })

        if player.has_accused:
            summary["accusations"].append(player.name)

    return summary
