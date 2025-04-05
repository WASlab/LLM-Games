from abc import ABC, abstractmethod
# Corrected import path assuming roles.py is inside mechanics
from mafia.enums import Faction
from typing import Optional, TYPE_CHECKING, Dict, Any

# Avoid circular import for type hinting
if TYPE_CHECKING:
    from mafia.player import Player
    from mafia.game_state import GameState


class Role(ABC):
    def __init__(self, name: str, faction: Faction):
        self.name = name
        self.faction = faction
        # Add alignment based on faction for consistency if needed elsewhere
        self.alignment = faction # Simple mapping for now

    @abstractmethod
    def get_role_description(self) -> str:
        """Return a string describing the role's abilities and goals."""
        pass

    def night_action(self, player: 'Player', game_state: 'GameState', target_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Executes the role's night action.
        Target selection logic is handled by the Agent/Player, passed via target_name.
        Returns a dictionary representing the action taken or None.
        """
        return None # Default: No night action

    def can_act_at_night(self) -> bool:
        """Checks if the role has a meaningful night action."""
        # Check if the night_action method is overridden from the base class
        return self.__class__.night_action != Role.night_action

    def __repr__(self):
        # Use self.faction directly as it's an attribute
        return f"<{self.faction.value}:{self.name}>"

# ------------------- TOWN ROLES -------------------

class Villager(Role):
    def __init__(self):
        # Use direct value for consistency, or reference an enum if preferred
        super().__init__("Villager", Faction.TOWN)

    def get_role_description(self) -> str:
        return "You are a Villager. You have no special abilities. Find and lynch the Mafia."

    # night_action is inherited as None

class Cop(Role):
    def __init__(self):
        super().__init__("Cop", Faction.TOWN)

    def get_role_description(self) -> str:
        return "You are the Cop. Each night, you can investigate one player to determine their faction (Town or Mafia)."

    def night_action(self, player: 'Player', game_state: 'GameState', target_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        target_player = game_state.get_player(target_name) if target_name else None

        if target_player and target_player.alive:
            # Simplified: Godfather reads as Town unless detectable=True (add later)
            is_mafia = target_player.role.faction == Faction.MAFIA
            # Handle Godfather detection rule here if needed
            # Example: if isinstance(target_player.role, Godfather) and not game_state.config.get("godfather_detectable", False):
            #     result_faction = Faction.TOWN
            # else:
            result_faction = Faction.MAFIA if is_mafia else Faction.TOWN

            result_info = f"Investigated {target_player.name}: Result {result_faction.value}"
            player.log_hidden(game_state, f"\uD83D\uDD0E {result_info}")
            # Store result in player's memory
            player.memory.append({
                "type": "investigation_result",
                "day": game_state.day_count,
                "target": target_player.name,
                "result": result_faction.value
            })
            # Action registered for logging/tracking, actual info given via memory
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
        target_player = game_state.get_player(target_name) if target_name else None

        if target_player and target_player.alive:
            # Protection handled centrally in night resolution based on this action
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

    # night_action is inherited as None (kill decision by Godfather)

class Godfather(Role):
    def __init__(self):
        super().__init__("Godfather", Faction.MAFIA)
        self.appears_as = Faction.TOWN # To cops, unless detectable

    def get_role_description(self) -> str:
        return ("You are the Godfather. You appear as Town to the Cop. "
                "Each night, choose a target for the Mafia to kill. "
                "If you die, a Goon will be promoted.")

    def night_action(self, player: 'Player', game_state: 'GameState', target_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        target_player = game_state.get_player(target_name) if target_name else None

        if target_player and target_player.alive:
            player.log_hidden(game_state, f"\uD83D\uDD2A Ordered kill on {target_player.name}")
            # Action registered, actual kill resolved centrally
            return {"type": "kill", "target": target_player.name}
        elif target_name:
             player.log_hidden(game_state, f"\uD83D\uDD2A Tried to order kill on {target_name}, but they were not found or dead.")
        return None

# Add other roles (RoleBlocker, Consigliere, etc.) here following the pattern...

# Helper function to get a role class from its name string (used in simulation setup)
# Place this at the end of the file or in a separate utility file
ROLE_CLASS_MAP = {
    "villager": Villager,
    "cop": Cop,
    "doctor": Doctor,
    "goon": Goon,
    "godfather": Godfather,
    # Add other roles here...
}

def get_role_class(role_name: str) -> Optional[type[Role]]:
    return ROLE_CLASS_MAP.get(role_name.lower())