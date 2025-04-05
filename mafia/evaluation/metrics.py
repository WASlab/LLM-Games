# mafia/evaluation/metrics.py
from collections import defaultdict
from typing import Dict, List


def compute_win_rate(games: List[Dict]) -> Dict[str, float]:
    """
    Returns the win rate for each faction based on finished games.
    """
    results = defaultdict(int)
    for game in games:
        results[game["winner"]] += 1
    total = sum(results.values())
    return {faction: wins / total for faction, wins in results.items()}


def compute_average_tokens(games: List[Dict]) -> Dict[str, float]:
    """
    Returns the average number of tokens used by each agent across games.
    """
    token_totals = defaultdict(int)
    token_counts = defaultdict(int)
    for game in games:
        for agent, tokens in game["tokens"].items():
            token_totals[agent] += tokens.get("input", 0) + tokens.get("output", 0)
            token_counts[agent] += 1
    return {
        agent: token_totals[agent] / token_counts[agent]
        for agent in token_totals
    }


def compute_average_role_accuracy(games: List[Dict]) -> float:
    """
    Computes how often role predictions were correct.
    """
    correct = 0
    total = 0
    for game in games:
        for entry in game["hidden_log"]:
            if "Predicted" in entry["info"]:
                # Format: "Predicted X as Y"
                parts = entry["info"].split()
                predicted_role = parts[-1]
                target = parts[1]
                actual_role = None
                for player in game["players"]:
                    if player["name"] == target:
                        actual_role = player["role"]
                        break
                if actual_role:
                    total += 1
                    if predicted_role == actual_role:
                        correct += 1
    return correct / total if total else 0.0
