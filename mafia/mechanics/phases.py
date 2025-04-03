# mafia/mechanics/phases.py

from mafia.enums import Phase
from mafia.game_state import GameState
from mafia.player import Player
from mafia.mechanics.roles import Role


def transition_to_day(game_state: GameState):
    """
    Executes night actions and moves the game to the day phase.
    This includes resolving kills, roleblocks, protections, and logging.
    """
    # Resolve night actions
    kills = []
    protections = set()

    for actor_name, action in game_state.night_actions.items():
        player = game_state.get_player(actor_name)
        if not player or not player.can_act():
            continue

        if 'kill' in action:
            target = action['kill']
            if target:
                kills.append(target.name)
                game_state.log_hidden(actor_name, f"Attempted kill on {target.name}")

        if 'investigation' in action:
            result = action['investigation']
            game_state.log_hidden(actor_name, f"Investigated: {result}")

        if 'protect' in action:
            target = action['protect']
            if target:
                protections.add(target.name)
                game_state.log_hidden(actor_name, f"Protected {target.name}")

        if 'roleblock' in action:
            target = action['roleblock']
            if target:
                target.is_roleblocked = True
                game_state.log_hidden(actor_name, f"Roleblocked {target.name}")

    # Resolve kills unless protected
    for target_name in kills:
        if target_name not in protections and game_state.is_alive(target_name):
            game_state.kill_player(target_name)
            game_state.messages.append(f"{target_name} was found dead in the morning.")
            game_state.log_hidden("system", f"{target_name} died during the night")

    # Reset states
    for player in game_state.players:
        player.reset_night_state()
        player.reset_day_state()

    game_state.reset_votes()
    game_state.reset_discussion_state()
    game_state.night_actions.clear()
    game_state.day_count += 1
    game_state.phase = Phase.DAY


def transition_to_night(game_state: GameState):
    """
    Ends the day phase, processes votes, and transitions to night.
    Includes resolving lynch and updating alive/dead lists.
    """
    # Process lynch
    if game_state.accused_player:
        votes_for_lynch = sum(game_state.lynch_confirm_votes.values())
        total_alive = len(game_state.alive_players)

        if votes_for_lynch > total_alive // 2:
            game_state.kill_player(game_state.accused_player)
            game_state.messages.append(f"{game_state.accused_player} was lynched.")
            game_state.log_hidden("system", f"{game_state.accused_player} was lynched by majority")
        else:
            game_state.messages.append(f"Nobody was lynched today.")

    game_state.phase = Phase.NIGHT
    game_state.reset_votes()
    game_state.reset_discussion_state()
