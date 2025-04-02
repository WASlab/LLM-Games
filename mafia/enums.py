from enum import Enum, auto


class Faction(Enum):
    TOWN = "town"
    MAFIA = "mafia"
    NEUTRAL = "neutral"  # Reserved for extensibility, not used in this environment


class GamePhase(Enum):
    NIGHT = "night"
    DAY_DISCUSSION = "day_discussion"
    VOTING = "voting"
    DEFENSE = "defense"
    FINAL_VOTE = "final_vote"
    GAME_OVER = "game_over"


class VoteType(Enum):
    ACCUSATION = "accusation"
    FINAL_GUILTY = "final_guilty"
    FINAL_INNOCENT = "final_innocent"
    SKIP = "skip"


class TownRole(Enum):
    VILLAGER = "villager"
    COP = "cop"               # Can investigate 1 player at night
    DOCTOR = "doctor"         # Can heal 1 player at night (prevent death)
    JAILOR = "jailor"         # Optional, executes privately (can skip for now)
    VETERAN = "veteran"       # Optional, stays in for TOS later

class MafiaRole(Enum):
    GOON = "goon"             # Basic mafia role
    GODFATHER = "godfather"   # Makes the kill decision
    ROLEBLOCKER = "roleblocker"  # Prevents action of one player at night
    CONSIGLIERE = "consigliere"  # Learns role of target at night
    BLACKMAILER = "blackmailer"  # Prevents player from speaking next day


class Alignment(Enum):
    TOWN = "town"
    MAFIA = "mafia"
    NONE = "none"  # For vanilla roles or roles with no investigative return


# Optional: reverse lookup to associate role enums with faction/alignment
ROLE_TO_FACTION = {
    TownRole.VILLAGER: Faction.TOWN,
    TownRole.COP: Faction.TOWN,
    TownRole.DOCTOR: Faction.TOWN,

    MafiaRole.GOON: Faction.MAFIA,
    MafiaRole.GODFATHER: Faction.MAFIA,
    MafiaRole.ROLEBLOCKER: Faction.MAFIA,
    MafiaRole.CONSIGLIERE: Faction.MAFIA,
    MafiaRole.BLACKMAILER: Faction.MAFIA,
}
