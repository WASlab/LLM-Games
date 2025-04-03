# mafia/roles.py

from abc import ABC, abstractmethod
from mafia.enums import Faction, TownRole, MafiaRole
from typing import Optional


class Role(ABC):
    def __init__(self, name: str, faction: Faction):
        self.name = name
        self.faction = faction

    @abstractmethod
    def night_action(self, player, game_state):
        """
        Optional: Override to implement role-specific night logic.
        Args:
            player: Player instance (the actor)
            game_state: The full game state (access to players, night actions, etc.)
        """
        pass

    def can_act_at_night(self) -> bool:
        return self.night_action.__func__ is not Role.night_action

    def __repr__(self):
        return f"<{self.faction.value}:{self.name}>"


# ------------------- TOWN ROLES -------------------

class Villager(Role):
    def __init__(self):
        super().__init__(TownRole.VILLAGER.value, Faction.TOWN)

    def night_action(self, player, game_state):
        return None  # No night action


class Cop(Role):
    def __init__(self):
        super().__init__(TownRole.COP.value, Faction.TOWN)

    def night_action(self, player, game_state):
        target = player.choose_target(game_state)
        if target and target.name in game_state.alive_players:
            result = "mafia" if target.role.faction == Faction.MAFIA else "town"
            player.log_hidden(game_state, f"🔍 Investigated {target.name}: {result}")
            return {"investigation": target.name, "faction": result}


class Doctor(Role):
    def __init__(self):
        super().__init__(TownRole.DOCTOR.value, Faction.TOWN)

    def night_action(self, player, game_state):
        target = player.choose_target(game_state)
        if target and target.name in game_state.alive_players:
            target.protected = True
            player.log_hidden(game_state, f"💉 Protected {target.name}")
            return {"protected": target.name}


# ------------------- MAFIA ROLES -------------------

class Goon(Role):
    def __init__(self):
        super().__init__(MafiaRole.GOON.value, Faction.MAFIA)

    def night_action(self, player, game_state):
        return None  # No solo night action


class Godfather(Role):
    def __init__(self):
        super().__init__(MafiaRole.GODFATHER.value, Faction.MAFIA)

    def night_action(self, player, game_state):
        target = player.choose_target(game_state)
        if target and target.name in game_state.alive_players:
            game_state.register_night_action(player.name, {"kill": target.name})
            player.log_hidden(game_state, f"☠️ Ordered hit on {target.name}")
            return {"kill": target.name}


class Roleblocker(Role):
    def __init__(self):
        super().__init__(MafiaRole.ROLEBLOCKER.value, Faction.MAFIA)

    def night_action(self, player, game_state):
        target = player.choose_target(game_state)
        if target and target.name in game_state.alive_players:
            target.is_roleblocked = True
            player.log_hidden(game_state, f"🚫 Roleblocked {target.name}")
            return {"roleblocked": target.name}


# ------------------- FACTORY FUNCTION -------------------

def create_role(role_name: str) -> Role:
    """Factory function to create roles from string name."""
    mapping = {
        "villager": Villager,
        "cop": Cop,
        "doctor": Doctor,
        "goon": Goon,
        "godfather": Godfather,
        "roleblocker": Roleblocker,
    }
    if role_name.lower() not in mapping:
        raise ValueError(f"Unknown role: {role_name}")
    return mapping[role_name.lower()]()
