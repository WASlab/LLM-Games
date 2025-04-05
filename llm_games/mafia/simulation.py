# === mafia/simulation.py ===

import os
import json
import uuid
from typing import Dict, List, Optional

from tqdm import tqdm

# Import your environment and other needed modules
from llm_games.mafia.environment import MafiaEnvironment
from llm_games.mafia.player import Player
from llm_games.mafia.mechanics.roles import get_role_class, Role
from llm_games.mafia.agents.rule_agent import RuleAgent
from llm_games.mafia.agents.llm_agent import LLMAgent  # Or your chosen LLM agent implementation

# Dummy Token Tracker if needed
class TokenTracker:
    """Placeholder for optional token counting or other usage stats."""
    def __init__(self):
        self.usage = {}

    def update(self, *args, **kwargs):
        pass

    def to_dict(self) -> Dict[str, Dict[str, int]]:
        return self.usage

def load_config_from_file(path: str) -> Dict:
    """
    Loads the configuration from a JSON or YAML file.
    For demonstration, returns a stub if not implemented.
    """
    print(f"Attempting to load config from {path} (placeholder).")
    # Real implementation might do:
    #   with open(path, "r") as f:
    #       return json.load(f)
    return {}

def create_players_from_config(config: Dict) -> List[Player]:
    """
    Creates Player objects with assigned roles and agents based on the config.
    Example config structure:
    {
      "roles": [
        {"name": "Player1", "role": "Cop"},
        {"name": "Player2", "role": "Doctor"},
        ...
      ],
      "agent_mapping": {
        "Player1": "llm",
        "Player4": "llm"
      },
      "llm_config": {
        "model": "gpt-3.5-turbo",
        ...
      },
      ...
    }
    """
    players = []
    roles_config = config.get("roles", [])

    # Fallback to a default 5-player setup if no roles provided
    if not roles_config:
        roles_setup = [
            ("Player1", "Cop"),
            ("Player2", "Doctor"),
            ("Player3", "Villager"),
            ("Player4", "Godfather"),
            ("Player5", "Goon")
        ]
        print("Warning: Using default 5-player role setup.")
    else:
        roles_setup = [(entry["name"], entry["role"]) for entry in roles_config]

    for name, role_name in roles_setup:
        RoleClass = get_role_class(role_name)
        if not RoleClass:
            raise ValueError(f"Unknown role name '{role_name}' in configuration.")
        role_instance = RoleClass()  # e.g., Cop(), Doctor()

        # Create the Player object
        player = Player(name=name, role=role_instance)

        # Agent assignment logic
        agent_type = config.get("agent_mapping", {}).get(name, "rule").lower()  # default 'rule'
        if agent_type == "llm":
            # Get additional details if available
            model_name = config.get("llm_config", {}).get("model", "gpt-3.5-turbo")
            system_prompt = f"You are {name}, playing Mafia as {role_instance.name}. {role_instance.get_role_description()}"
            
            # Dummy model backend for testing
            def dummy_model_backend(prompt: str) -> str:
                return '{"action": "pass"}'
            
            agent = LLMAgent(
                name=name,
                model_backend=dummy_model_backend,
                tokenizer=None,
                config={"system_prompt": system_prompt, "model": model_name}
            )
            print(f"Assigning LLM-based Agent to {name} ({role_name})")
        else:
            # Default to a rule-based agent
            strategy = config.get("agent_strategy", {})
            agent = RuleAgent(name=name, player_role=role_instance.name, strategy=strategy)
            print(f"Assigning RuleAgent to {name} ({role_name})")

        player.agent = agent
        players.append(player)

    return players

def log_game_summary(game_state) -> Dict:
    """
    Summarizes final game results.
    """
    return {
        "game_id": game_state.game_id,
        "winner": game_state.winner.value if game_state.winner else None,
        "final_roles": game_state.final_player_roles,
        "day_count": game_state.day_count
    }

def run_simulation(game_config: Dict, agent_config: Dict) -> Dict:
    """
    Runs a single Mafia game simulation with the specified configuration and agent settings.
    Returns a summary dictionary of the final game state.
    """
    combined_config = {**game_config, "agents": agent_config}

    # 1. Create players
    players = create_players_from_config(combined_config)

    # 2. Create environment
    env = MafiaEnvironment(players=players, config=combined_config)

    # For quick testing, force the initial phase to DAY_DISCUSSION if desired.
    if env.state.phase == env.state.phase.__class__.NIGHT:
        print("Forcing initial phase to DAY_DISCUSSION for testing.")
        env._transition_to_day()

    token_tracker = TokenTracker()

    # 3. Main game loop
    max_steps = combined_config.get("max_steps", 100)
    step_count = 0

    while not env.state.game_over and step_count < max_steps:
        step_count += 1
        print(f"\n=== [Step {step_count}] Day {env.state.day_count}, Phase: {env.state.phase.name}, Turn: {env.state.turn_number_in_phase} ===")

        current_player_name = env.get_current_player_name()
        if not current_player_name:
            # No current player; advance phase
            env.step_phase()
            continue

        player = env.state.get_player(current_player_name)
        if not player or not player.alive:
            env.advance_turn()
            continue

        # Build observation for the current player
        observation = env.get_observation(current_player_name)

        # Ensure agent observes the environment first
        agent = player.agent
        agent.observe(observation)
        agent_action = agent.act()
        print(f"{current_player_name} (role={player.role.name}) chooses: {agent_action}")

        success = env.process_player_action(current_player_name, agent_action)
        if not success:
            print(f"Action failed or was invalid: {agent_action}")

        # Optionally update token usage
        # token_tracker.update(current_player_name, observation, agent_action)

    print("\n=== Game Over ===")
    winner_str = env.state.winner.value if env.state.winner else "No winner / Undecided"
    print(f"Winner: {winner_str}")
    print(f"Ended on Day {env.state.day_count}, Phase: {env.state.phase.name}")

    summary = log_game_summary(env.state)
    summary["tokens_used"] = token_tracker.to_dict()
    return summary

def run_multiple_simulations(num_games: int = 5,
                             config_path: str = "config/default_game.json",
                             save_dir: str = "output/sim_results"):
    """
    Runs multiple simulations, saving results as JSON Lines.
    """
    os.makedirs(save_dir, exist_ok=True)
    base_game_config = load_config_from_file(config_path)
    if not base_game_config:
        base_game_config = {
            "roles": [
                {"name": "Player1", "role": "Cop"},
                {"name": "Player2", "role": "Doctor"},
                {"name": "Player3", "role": "Villager"},
                {"name": "Player4", "role": "Godfather"},
                {"name": "Player5", "role": "Goon"}
            ],
            "agent_mapping": {
                "Player1": "llm",
                "Player4": "llm"
            },
            "llm_config": {
                "model": "gpt-3.5-turbo"
            },
            "max_steps": 100
        }
    base_agent_config = {}

    game_results = []
    log_file = os.path.join(save_dir, "games_log.jsonl")

    for _ in tqdm(range(num_games), desc="Simulating Games"):
        game_id = str(uuid.uuid4())
        current_game_config = {**base_game_config, "game_id": game_id}

        try:
            result = run_simulation(current_game_config, base_agent_config)
            result["game_id"] = game_id
            game_results.append(result)
            with open(log_file, "a", encoding="utf-8") as f:
                json.dump(result, f)
                f.write("\n")
        except Exception as e:
            print(f"Error in simulation {game_id}: {e}")
            error_info = {
                "game_id": game_id,
                "error": str(e),
                "status": "error"
            }
            with open(log_file, "a", encoding="utf-8") as f:
                json.dump(error_info, f)
                f.write("\n")

    print(f"\n=== Simulations Complete ===\nLogs saved to {log_file}")
    # Optionally perform aggregate analysis here

def main():
    """CLI entrypoint for running simulations."""
    run_multiple_simulations(num_games=3)

if __name__ == "__main__":
    main()
