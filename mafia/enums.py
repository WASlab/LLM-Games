from enum import Enum

class Faction(Enum):
    TOWN = "town"
    MAFIA = "mafia"
    NEUTRAL = "neutral" # Reserved for extensibility

class GamePhase(Enum):
    NIGHT = "night"
    DAY_DISCUSSION = "day_discussion"
    VOTING = "voting"
    DEFENSE = "defense" # Optional phase if accusation needs defense
    FINAL_VOTE = "final_vote" # Optional phase for final lynch decision
    GAME_OVER = "game_over"

class VoteType(Enum):
    ACCUSATION = "accusation" # Initial vote during day
    FINAL_GUILTY = "final_guilty" # Vote during final lynch
    FINAL_INNOCENT = "final_innocent" # Vote during final lynch
    SKIP = "skip" # Abstain from voting