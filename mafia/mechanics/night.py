# mafia/mechanics/night.py

from mafia.enums import RoleType
from mafia.game_state import GameState

def resolve_night_phase(game_state: GameState):
    """
    Resolves all night actions in the game. This includes mafia kills,
    investigations, roleblocks, protections, etc. Follows a standard resolution order.
    """
    # Stage 1: Apply roleblocks
    roleblocked = set()
    for actor, action in game_state.night_actions.items():
        if action.get("type") == "roleblock":
            target = action.get("target")
            roleblocked.add(target)

    # Stage 2: Apply protection
    protected = set()
    for actor, action in game_state.night_actions.items():
        if action.get("type") == "protect":
            target = action.get("target")
            if target not in roleblocked:
                protected.add(target)

    # Stage 3: Apply mafia kills (Godfather priority)
    kill_targets = []
    for actor, action in game_state.night_actions.items():
        if action.get("type") == "kill":
            if actor in roleblocked:
                continue
            target = action.get("target")
            if target not in protected:
                kill_targets.append(target)

    for target in kill_targets:
        if game_state.is_alive(target):
            game_state.kill_player(target)
            game_state.messages.append(f"{target} was killed during the night.")

    # Stage 4: Investigations (e.g., Cop)
    for actor, action in game_state.night_actions.items():
        if action.get("type") == "investigate" and actor not in roleblocked:
            target = action.get("target")
            player_obj = game_state.get_player(target)
            result = {
                "target": target,
                "alignment": player_obj.role.alignment if player_obj else "unknown"
            }
            investigator = game_state.get_player(actor)
            if investigator:
                investigator.memory.append(result)

    # Stage 5: Cleanup
    game_state.night_actions.clear()
