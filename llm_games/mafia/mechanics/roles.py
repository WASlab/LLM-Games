# === mafia/mechanics/roles.py ===

from abc import ABC, abstractmethod
from llm_games.mafia.enums import Faction
from typing import Optional, TYPE_CHECKING, Dict, Any, List

# Avoid circular import for type hinting
if TYPE_CHECKING:
    from llm_games.mafia.player import Player
    from llm_games.mafia.game_state import GameState

class Role(ABC):
    def __init__(self, name: str, faction: Faction):
        self.name = name
        self.faction = faction
        # For now, we use faction as the alignment. Override if needed.
        self.alignment = faction

    @abstractmethod
    def get_role_description(self) -> str:
        """Return a string describing the role's abilities and goals."""
        pass

    def night_action(self, player: 'Player', game_state: 'GameState', target_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Executes the role's night action.
        Target selection logic is handled by the agent/player.
        Returns a dict representing the action taken, or None.
        """
        return None  # Default: No night action

    def can_act_at_night(self) -> bool:
        """Checks if the role has a meaningful night action."""
        return self.__class__.night_action != Role.night_action

    def get_available_targets(self, player: 'Player', game_state: 'GameState') -> List[str]:
        """
        Returns a list of valid target player names.
        Default: any alive player except self.
        Override to add additional filters.
        """
        return [p.name for p in game_state.players if p.alive and p.name != player.name]

    def win_condition_met(self, player: 'Player', game_state: 'GameState') -> Optional[bool]:
        """
        Stub for roles with unique win conditions.
        Returns True if the player's win condition is met,
        False if failed, or None if undecided.
        """
        return None  # Default: rely on faction win

    def get_llm_schema(self) -> Dict[str, Any]:
        """
        Returns a dictionary with structured information about the role,
        useful for prompting LLM-based agents.
        """
        return {
            "name": self.name,
            "faction": self.faction.value,
            "alignment": self.alignment.value,
            "can_act_at_night": str(self.can_act_at_night()),
            "description": self.get_role_description()
        }

    def __repr__(self):
        return f"<{self.faction.value}:{self.name}>"

# ------------------- TOWN ROLES -------------------

class Villager(Role):
    def __init__(self):
        super().__init__("Villager", Faction.TOWN)

    def get_role_description(self) -> str:
        return "You are a Villager. You have no special abilities. Find and lynch the Mafia."

    # Inherits default night_action (None)

class Cop(Role):
    def __init__(self):
        super().__init__("Cop", Faction.TOWN)

    def get_role_description(self) -> str:
        return "You are the Cop. Each night, you can investigate one player to determine their faction (Town or Mafia)."

    def night_action(self, player: 'Player', game_state: 'GameState', target_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        # Prevent self-investigation
        if target_name == player.name:
            player.log_hidden(game_state, "You cannot investigate yourself.")
            return None

        target_player = game_state.get_player(target_name) if target_name else None
        if target_player and target_player.alive:
            # Handle Godfather detection: if target is a Godfather and game config dictates, appear as Town
            if isinstance(target_player.role, Godfather) and not game_state.game_config.get("godfather_detectable", False):
                result_faction = Faction.TOWN
            else:
                result_faction = target_player.role.faction

            result_info = f"Investigated {target_player.name}: Result {result_faction.value}"
            player.log_hidden(game_state, f"\uD83D\uDD0E {result_info}")
            player.memory.append({
                "type": "investigation_result",
                "day": game_state.day_count,
                "target": target_player.name,
                "result": result_faction.value
            })
            return {"type": "investigate", "target": target_player.name, "result": result_faction.value}
        elif target_name:
            player.log_hidden(game_state, f"\uD83D\uDD0E Tried to investigate {target_name}, but they were not found or dead.")
        return None

class Doctor(Role):
    def __init__(self):
        super().__init__("Doctor", Faction.TOWN)

    def get_role_description(self) -> str:
        return "You are the Doctor. Each night, you can choose one player to protect from death."

    def night_action(self, player: 'Player', game_state: 'GameState', target_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        # Optionally, disallow self-protection based on configuration.
        if target_name == player.name and not game_state.game_config.get("doctor_can_self_heal", True):
            player.log_hidden(game_state, "You cannot protect yourself tonight.")
            return None

        target_player = game_state.get_player(target_name) if target_name else None
        if target_player and target_player.alive:
            player.log_hidden(game_state, f"\uD83E\uDE78 Protected {target_player.name}")
            return {"type": "protect", "target": target_player.name}
        elif target_name:
            player.log_hidden(game_state, f"\uD83E\uDE78 Tried to protect {target_name}, but they were not found or dead.")
        return None

# ------------------- MAFIA ROLES -------------------

class Goon(Role):
    def __init__(self):
        super().__init__("Goon", Faction.MAFIA)

    def get_role_description(self) -> str:
        return "You are a Mafia Goon. Work with your team to kill Town members at night and avoid getting lynched during the day."

    # Inherits default night_action (None)

class Godfather(Role):
    def __init__(self):
        super().__init__("Godfather", Faction.MAFIA)
        self.appears_as = Faction.TOWN  # To cops, unless detectable

    def get_role_description(self) -> str:
        return ("You are the Godfather. You appear as Town to the Cop. "
                "Each night, choose a target for the Mafia to kill. "
                "If you die, a Goon will be promoted.")

    def night_action(self, player: 'Player', game_state: 'GameState', target_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        # Prevent self-targeting or targeting fellow Mafia
        if target_name == player.name:
            player.log_hidden(game_state, "You cannot target yourself.")
            return None
        target_player = game_state.get_player(target_name) if target_name else None
        if target_player:
            if target_player.faction == Faction.MAFIA:
                player.log_hidden(game_state, "You cannot order a kill on a fellow Mafia member.")
                return None
        if target_player and target_player.alive:
            player.log_hidden(game_state, f"\uD83D\uDD2A Ordered kill on {target_player.name}")
            return {"type": "kill", "target": target_player.name}
        elif target_name:
            player.log_hidden(game_state, f"\uD83D\uDD2A Tried to order kill on {target_name}, but they were not found or dead.")
        return None

# ------------------- NEW ROLES -------------------

class RoleBlocker(Role):
    def __init__(self):
        super().__init__("RoleBlocker", Faction.MAFIA)

    def get_role_description(self) -> str:
        return "You are the RoleBlocker. Each night, you can block another player's action."

    def night_action(self, player: 'Player', game_state: 'GameState', target_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        # Prevent blocking self
        if target_name == player.name:
            player.log_hidden(game_state, "You cannot roleblock yourself.")
            return None
        target_player = game_state.get_player(target_name) if target_name else None
        if target_player and target_player.alive:
            player.log_hidden(game_state, f"Blocked {target_player.name}'s action")
            return {"type": "roleblock", "target": target_player.name}
        elif target_name:
            player.log_hidden(game_state, f"Tried to block {target_name}, but they were not found or dead.")
        return None

class Consigliere(Role):
    def __init__(self):
        super().__init__("Consigliere", Faction.MAFIA)

    def get_role_description(self) -> str:
        return "You are the Consigliere. Each night, you may learn the exact role of one player."

    def night_action(self, player: 'Player', game_state: 'GameState', target_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        target_player = game_state.get_player(target_name) if target_name else None
        if target_player and target_player.alive:
            role_name = target_player.role.name
            player.log_hidden(game_state, f"Investigated {target_player.name}: Role = {role_name}")
            player.memory.append({
                "type": "role_peek",
                "day": game_state.day_count,
                "target": target_player.name,
                "role": role_name
            })
            return {"type": "consigliere_investigate", "target": target_player.name, "result": role_name}
        elif target_name:
            player.log_hidden(game_state, f"Tried to investigate {target_name}, but they were not found or dead.")
        return None

# ------------------- OPTIONAL HELPER METHODS -------------------

# These can be overridden by individual roles if needed.
# For example, a role may override win_condition_met for unique victory conditions.
def default_win_condition(player: 'Player', game_state: 'GameState') -> Optional[bool]:
    return None

# ------------------- ROLE REGISTRY -------------------

ROLE_CLASS_MAP = {
    "villager": Villager,
    "cop": Cop,
    "doctor": Doctor,
    "goon": Goon,
    "godfather": Godfather,
    "roleblocker": RoleBlocker,
    "consigliere": Consigliere,
    # Add additional roles here...
}

def get_role_class(role_name: str) -> Optional[type[Role]]:
    return ROLE_CLASS_MAP.get(role_name.lower())
