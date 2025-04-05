import os
import json
from tqdm import tqdm
# Use correct Environment class name
from mafia.environment import MafiaEnvironment
# Import role classes and helper
from mafia.mechanics.roles import get_role_class, Role
from mafia.player import Player
# Keep TokenTracker import, assume it exists or create dummy
# from mafia.utils.token_cost import TokenTracker # If using
# Import agent classes
from mafia.agents.rule_agent import RuleBasedAgent # Assuming this will exist
from mafia.agents.llm_agent import LLMAPIClientAgent # Import the LLM agent
from typing import Dict, List
import uuid

# Dummy Token Tracker if needed
class TokenTracker:
    def __init__(self): self.usage = {}
    def update(self, *args, **kwargs): pass
    def to_dict(self): return self.usage

def create_players_from_config(config: Dict) -> List[Player]:
    """Creates Player objects based on a configuration dictionary."""
    players = []
    roles_config = config.get("roles", []) # e.g., [{"name": "Player1", "role": "Cop"}, ...]
    if not roles_config: # Fallback to default if config is empty/missing roles
        roles_setup = [
            ("Player1", "Cop"), ("Player2", "Doctor"), ("Player3", "Villager"),
            ("Player4", "Godfather"), ("Player5", "Goon")
        ]
        print("Warning: Using default 5-player role setup.")
    else:
        roles_setup = [(p_cfg["name"], p_cfg["role"]) for p_cfg in roles_config]

    for name, role_name in roles_setup:
        RoleClass = get_role_class(role_name)
        if not RoleClass:
             raise ValueError(f"Unknown role name '{role_name}' in configuration.")
        role_instance = RoleClass()
        player = Player(name=name, role=role_instance)

        # --- Agent Assignment ---
        # Example: Assign agents based on config or default to RuleBased
        agent_type = config.get("agent_mapping", {}).get(name, "rule") # Default to rule-based

        if agent_type.lower() == "llm":
            # TODO: Get model name, system prompt from config
            model_name = config.get("llm_config", {}).get("model", "gpt-4") # Example default
            system_prompt_key = config.get("llm_config", {}).get("system_prompt_key", "default_mafia")
            # Need a way to load system prompts based on key
            system_prompt = f"You are {name}, playing Mafia as {role_instance.name}. {role_instance.get_role_description()}" # Basic example
            agent = LLMAPIClientAgent(name=name, model=model_name, system_prompt=system_prompt)
            print(f"Assigning LLM Agent ({model_name}) to {name}")
        else: # Default to RuleBasedAgent
             # RuleBasedAgent needs to be implemented
            agent = RuleBasedAgent(name=name, player_role=role_instance.name)
            print(f"Assigning Rule Agent to {name}")

        # Link agent to player (though environment might manage this)
        player.agent = agent # Store agent reference if needed directly by player, otherwise managed by env/runner
        players.append(player)

    return players


def run_simulation(game_config: Dict, agent_config: Dict) -> Dict:
    """Runs a single game simulation and returns the final state."""
    print(f"\n--- Starting Simulation Game ID: {game_config.get('game_id', 'N/A')} ---")

    # Combine configs or pass separately
    full_config = {**game_config, "agents": agent_config} # Example merge

    # Create players based on combined config
    players = create_players_from_config(full_config) # Pass merged config

    # Initialize environment
    # Pass game_config to environment if it needs rules like GF detectability
    env = MafiaEnvironment(players=players, config=full_config)
    token_tracker = TokenTracker() # Initialize token tracker if used

    # --- Game Loop ---
    max_steps = full_config.get("max_steps", 100) # Limit game length
    step_count = 0
    while not env.state.game_over and step_count < max_steps:
        step_count += 1
        print(f"\n=== Day {env.state.day_count} | Phase: {env.state.phase.name} | Turn: {env.state.turn_number_in_phase} ===")
        current_player_name = env.get_current_player_name() # Needs implementation in Env

        if not current_player_name:
            # Environment handles transition or phase resolution automatically
             print("Environment resolving phase...")
             env.step_phase() # Needs implementation in Env
             continue # Go to next loop iteration to check game state

        player = env.state.get_player(current_player_name)
        if not player or not player.alive:
             print(f"Skipping turn for {current_player_name} (dead or invalid).")
             env.advance_turn() # Needs implementation in Env
             continue

        agent = player.agent # Get agent associated with the player

        # Get observation for the current player
        observation = env.get_observation(current_player_name) # Needs implementation in Env

        # Agent decides action
        print(f"--- {current_player_name}'s Turn ({agent.__class__.__name__}) ---")
        action = agent.act(observation) # Agent returns action dict
        print(f"Action chosen: {action}")

        # Environment processes action
        success = env.process_player_action(current_player_name, action) # Needs implementation in Env
        if not success:
            print(f"Action {action} failed or was invalid.")

        # Optional: Track tokens
        # token_tracker.update(current_player_name, observation, action)

        # Environment potentially advances turn or phase based on action
        # This might happen inside process_player_action or require a separate env.advance() call

    print(f"\n--- Game Over ---")
    print(f"Winner: {env.state.winner.value if env.state.winner else 'Draw/Timeout'}")
    print(f"Ended on Day {env.state.day_count}, Phase {env.state.phase.name}")

    # Log final state and return results
    final_state_summary = log_game_summary(env.state) # Use analysis function
    final_state_summary["tokens_used"] = token_tracker.to_dict() # Add token info if tracked
    return final_state_summary


def run_multiple_simulations(num_games=10, config_path="config/default_game.json", save_dir="data/episodes"):
    """Runs multiple simulations based on a config file."""
    os.makedirs(save_dir, exist_ok=True)

    # Load base configuration (needs implementation)
    # base_game_config = load_config_from_file(config_path)
    # base_agent_config = base_game_config.get("agent_config", {}) # Separate agent config if needed
    base_game_config = {"roles": [ # Example default config
             {"name": "Player1", "role": "Cop"}, {"name": "Player2", "role": "Doctor"},
             {"name": "Player3", "role": "Villager"}, {"name": "Player4", "role": "Godfather"},
             {"name": "Player5", "role": "Goon"}
         ],
        "agent_mapping": {"Player1": "llm", "Player4": "llm"}, # P1 & P4 are LLMs
        "llm_config": {"model": "gpt-3.5-turbo"} # Example LLM config
     }
    base_agent_config = {} # Agent specific settings if needed


    game_results = []
    for i in tqdm(range(num_games), desc="Simulating Games"):
        game_id = str(uuid.uuid4())
        current_game_config = {**base_game_config, "game_id": game_id}
        # Add variations here if doing experiments (e.g., change roles, prompts)

        try:
            result = run_simulation(current_game_config, base_agent_config)
            game_results.append(result)

            # Save individual game logs as JSONL
            log_path = os.path.join(save_dir, "games_log.jsonl")
            with open(log_path, "a") as f:
                json.dump(result, f)
                f.write("\n")

        except Exception as e:
            print(f"\n!!!!!! Error during simulation {game_id} !!!!!!")
            print(f"Error: {e}")
            # Log error state if possible
            error_info = {"game_id": game_id, "status": "error", "error_message": str(e)}
            log_path = os.path.join(save_dir, "games_log.jsonl")
            with open(log_path, "a") as f:
                json.dump(error_info, f)
                f.write("\n")


    print(f"\n--- Simulation Run Complete ---")
    print(f"Saved {len(game_results)} game logs to {os.path.join(save_dir, 'games_log.jsonl')}")

    # --- Optional: Compute and print aggregate metrics ---
    # win_rates = compute_win_rate(game_results)
    # avg_tokens = compute_average_tokens(game_results)
    # avg_accuracy = compute_average_role_accuracy(game_results)
    # print("\nAggregate Metrics:")
    # print(f"Win Rates: {win_rates}")
    # print(f"Avg Tokens: {avg_tokens}")
    # print(f"Avg Role Accuracy: {avg_accuracy}")


# Helper for loading config (placeholder)
def load_config_from_file(path: str) -> Dict:
     print(f"Warning: Config loading not implemented. Using defaults. Tried path: {path}")
     # Implement actual JSON/YAML loading here
     return {}


# Need log_game_summary, compute_* from evaluation module
# Placeholder if not implemented yet
def log_game_summary(game_state): return {"game_id": game_state.game_id, "winner": game_state.winner.value if game_state.winner else None, "final_roles": game_state.final_player_roles}
# def compute_win_rate(results): return {}
# def compute_average_tokens(results): return {}
# def compute_average_role_accuracy(results): return 0.0


if __name__ == "__main__":
    # Example of how to run
    run_multiple_simulations(num_games=5, save_dir="output/sim_results")
