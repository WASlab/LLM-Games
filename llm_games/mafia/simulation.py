# === mafia/simulation.py ===

import os
import json
import uuid
from typing import Dict, List, Optional

from tqdm import tqdm # Keep tqdm for progress bars

# Core project imports
from llm_games.mafia.environment import MafiaEnvironment
from llm_games.mafia.player import Player
from llm_games.mafia.mechanics.roles import get_role_class
from llm_games.mafia.agents.rule_agent import RuleAgent
from llm_games.mafia.agents.llm_agent import LLMAgent # Use the updated LLMAgent
from llm_games.mafia.enums import GamePhase, Faction # Import Faction for logging

# Basic Token Tracker (can be replaced with a more sophisticated one if needed)
class TokenTracker:
    def __init__(self):
        self.usage: Dict[str, Dict[str, int]] = {} # agent_name -> {"input": X, "output": Y}

    def update(self, agent_name: str, input_tokens: int = 0, output_tokens: int = 0):
        if agent_name not in self.usage:
            self.usage[agent_name] = {"input": 0, "output": 0}
        self.usage[agent_name]["input"] += input_tokens
        self.usage[agent_name]["output"] += output_tokens

    def to_dict(self) -> Dict[str, Dict[str, int]]:
        return dict(self.usage)

# Configuration Loading (Simple placeholder)
def load_config_from_file(path: str) -> Dict:
    """Loads game configuration from a JSON file."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            print(f"Successfully loaded configuration from {path}")
            return config
    except FileNotFoundError:
        print(f"Warning: Configuration file not found at {path}. Using default settings.")
        return {}
    except json.JSONDecodeError:
        print(f"Warning: Error decoding JSON from {path}. Using default settings.")
        return {}
    except Exception as e:
        print(f"Warning: An unexpected error occurred loading config from {path}: {e}. Using default settings.")
        return {}


def create_players_from_config(config: Dict) -> List[Player]:
    """Creates Player objects with assigned roles and agents based on the config."""
    players: List[Player] = []
    roles_config = config.get("roles", [])

    # Default setup if no roles are specified in config
    if not roles_config:
        print("Warning: No roles specified in config. Using default 5-player setup (Cop, Doctor, Villager, Godfather, Goon).")
        roles_config = [
            {"name": "Player1", "role": "Cop"},
            {"name": "Player2", "role": "Doctor"},
            {"name": "Player3", "role": "Villager"},
            {"name": "Player4", "role": "Godfather"},
            {"name": "Player5", "role": "Goon"}
        ]
        # Default agent mapping if none provided for the default roles
        if "agent_mapping" not in config:
             config["agent_mapping"] = {p["name"]: "rule" for p in roles_config}
             config["agent_mapping"]["Player1"] = "llm" # Example: Make Player1 an LLM by default
             config["agent_mapping"]["Player4"] = "llm" # Example: Make Player4 an LLM by default

    # Create players and assign agents
    agent_mapping = config.get("agent_mapping", {})
    llm_agent_config = config.get("llm_agent_config", {}) # Global LLM agent config
    rule_agent_strategy = config.get("rule_agent_strategy", {}) # Global Rule agent strategy

    for role_entry in roles_config:
        name = role_entry.get("name")
        role_name = role_entry.get("role")
        if not name or not role_name:
            print(f"Warning: Skipping invalid role entry in config: {role_entry}")
            continue

        RoleClass = get_role_class(role_name)
        if not RoleClass:
            print(f"Error: Unknown role name '{role_name}' for player {name}. Skipping.")
            # Or raise ValueError(f"Unknown role name '{role_name}'...")
            continue
        role_instance = RoleClass()
        player = Player(name=name, role=role_instance) # Create the player first

        # Determine agent type for this player
        agent_type = agent_mapping.get(name, "rule").lower() # Default to rule-based if not specified

        # Create the agent instance
        if agent_type == "llm":
            # Pass the specific player's name and potentially override global LLM config
            agent_specific_config = llm_agent_config.copy() # Start with global config
            agent_specific_config.update(role_entry.get("agent_config", {})) # Layer role-specific config
            # Ensure backend_type is set, default to dummy if needed
            if "backend_type" not in agent_specific_config:
                 agent_specific_config["backend_type"] = "dummy"

            agent = LLMAgent(
                name=name,
                config=agent_specific_config # Pass the combined config
            )
            print(f"  - Assigning LLMAgent ({agent.backend_type}/{agent.model_identifier}) to {name} ({role_name})")
        else: # Default to RuleAgent
            agent_specific_strategy = rule_agent_strategy.copy()
            agent_specific_strategy.update(role_entry.get("agent_strategy", {}))
            agent = RuleAgent(
                name=name,
                role=role_instance.name, # Pass the role name for rule logic
                strategy=agent_specific_strategy
             )
            print(f"  - Assigning RuleAgent to {name} ({role_name})")

        player.agent = agent # Assign the created agent to the player
        players.append(player)

    if not players:
         raise ValueError("No valid players could be created from the configuration.")

    return players


def log_game_summary(game_state, token_tracker: TokenTracker) -> Dict:
    """Creates a dictionary summarizing the completed game's results."""
    summary = {
        "game_id": game_state.game_id,
        "winner": game_state.winner.value if game_state.winner else "UNDECIDED",
        "final_roles": game_state.final_player_roles,
        "day_count": game_state.day_count,
        "total_steps": game_state.turn_number_in_phase, # Or track total steps separately
        "game_over_phase": game_state.phase.name,
        "alive_at_end": sorted(list(game_state.alive_players)),
        "dead_at_end": sorted(list(game_state.dead_players)),
        "token_usage": token_tracker.to_dict(),
        # Consider adding full message log or hidden log if needed for detailed analysis
        # "messages": [msg.to_dict() for msg in game_state.messages],
        # "hidden_log": list(game_state.hidden_log),
    }
    return summary


def run_simulation(game_config: Dict, agent_config: Optional[Dict]=None) -> Dict:
    """Runs a single game simulation from start to finish."""

    # --- Setup ---
    sim_id = game_config.get("game_id", str(uuid.uuid4()))
    print(f"\n--- Starting Mafia Simulation [ID: {sim_id}] ---")

    # Merge game_config and agent_config (agent_config is now primarily for LLMs)
    # The primary way to configure agents is now within the "roles" list in game_config
    # or using global configs like "llm_agent_config" and "rule_agent_strategy".
    combined_config = game_config.copy()
    if agent_config: # For backward compatibility or global overrides
        combined_config["llm_agent_config"] = {**combined_config.get("llm_agent_config", {}), **agent_config}


    print("Creating players and agents...")
    try:
        players = create_players_from_config(combined_config)
    except ValueError as e:
        print(f"Error setting up players: {e}")
        return {"game_id": sim_id, "status": "error", "message": str(e)}

    print("Initializing environment...")
    env = MafiaEnvironment(players=players, config=combined_config)
    env.state.game_id = sim_id # Ensure game state uses the provided ID

    token_tracker = TokenTracker() # Initialize token tracker
    max_steps = combined_config.get("max_steps", 150) # Sensible default max steps
    step_count = 0
    action_log = [] # Store (step, player, action) tuples

    print(f"Game starting... Max steps: {max_steps}")
    env.state.log_message("system", f"Simulation Start. Max steps: {max_steps}", msg_type="system")

    # --- Simulation Loop ---
    while not env.state.game_over and step_count < max_steps:
        step_count += 1
        current_phase = env.state.phase
        current_player_name = env.get_current_player_name() # Might be None

        print(f"\n>>> [Step {step_count}/{max_steps}] Day {env.state.day_count} | Phase: {current_phase.name} | Turn: {env.state.turn_number_in_phase} | Player: {current_player_name or 'System'} <<<")

        # --- Handle Phase Transitions / System Actions ---
        if current_player_name is None and current_phase not in {GamePhase.FINAL_VOTE, GamePhase.GAME_OVER}:
            # Environment needs to resolve something (e.g., night actions) or transition phase
            print("System turn: Resolving phase actions or transitioning...")
            phase_ended_game = env.step_phase() # step_phase advances state and returns True if game ends
            if phase_ended_game:
                 print("Game ended during system resolution.")
                 break
            continue # Move to next step after system action

        # --- Handle Player Actions ---
        active_players_in_phase: List[str] = []
        if current_phase == GamePhase.NIGHT:
             # All players with night actions act 'simultaneously' (submit actions)
             active_players_in_phase = [p.name for p in players if p.alive and p.can_act_at_night()]
             if not active_players_in_phase:
                  print("No players with night actions this night.")
                  env.step_phase() # Resolve night immediately
                  continue
        elif current_phase == GamePhase.FINAL_VOTE:
             # All alive players vote
             active_players_in_phase = list(env.state.alive_players)
             if not active_players_in_phase:
                  print("No alive players to conduct final vote.")
                  env.step_phase()
                  continue
        elif current_phase == GamePhase.DEFENSE:
             # Only the player on trial acts
             if env.state.player_on_trial and env.state.is_alive(env.state.player_on_trial):
                  active_players_in_phase = [env.state.player_on_trial]
             else:
                   print(f"Player on trial ({env.state.player_on_trial}) not available for defense.")
                   env.step_phase() # Move to final vote
                   continue
        elif current_phase == GamePhase.DAY_DISCUSSION:
             # Only the current player acts
             if current_player_name and env.state.is_alive(current_player_name):
                 active_players_in_phase = [current_player_name]
             elif current_player_name:
                  print(f"Skipping turn for {current_player_name} (dead or invalid).")
                  env.advance_turn() # Advance to next speaker
                  continue
             else: # Should have been caught earlier, but safety check
                  print("Error: Day discussion but no current player turn.")
                  env.step_phase() # Try to recover
                  continue
        elif current_phase == GamePhase.VOTING:
             # Handle initial voting if implemented - assuming merged into discussion/final vote for now
             print("Standard voting phase - assuming handled by accusation/final vote logic.")
             env.step_phase() # Skip this phase if logic isn't distinct
             continue
        else: # Game Over or unexpected state
              print(f"Phase {current_phase.name} does not require player actions or is unexpected.")
              break # Exit loop if game over

        # --- Process Actions for Active Players ---
        actions_processed_this_step = 0
        for p_name in active_players_in_phase:
            player = env.state.get_player(p_name)
            if not player or not player.alive:
                print(f"Skipping action for {p_name} (not found or dead).")
                continue

            # Get observation for the player
            observation = env.get_observation(p_name)

            # Agent decision
            agent = player.agent
            if not agent:
                 print(f"Error: Player {p_name} has no assigned agent!")
                 action = {"action": "pass", "content": "Agent missing."}
            else:
                 agent.observe(observation) # Agent sees the state
                 action = agent.act() # Agent decides action

            print(f"  - {p_name} ({player.role.name} / {player.faction.value}) chose: {action}")
            action_log.append((step_count, p_name, action)) # Log the chosen action

            # Environment processes the action
            success = env.process_player_action(p_name, action)
            if not success:
                print(f"    -> Action by {p_name} failed or was invalid.")
                # Optionally, give agent another chance or force pass? For now, just log.
                env.state.log_hidden(p_name, f"Action failed: {action}")

            actions_processed_this_step += 1
            # Note: Token tracking would happen within LLMAgent.act() or via callbacks

        # --- Advance Game State After Actions ---
        if current_phase == GamePhase.NIGHT:
             # After all night actions are submitted, resolve them and transition
             print("Resolving night actions...")
             env.step_phase()
        elif current_phase == GamePhase.FINAL_VOTE:
             # After all votes are cast, resolve the lynch and transition
             print("Resolving final votes...")
             env.step_phase()
        elif current_phase == GamePhase.DEFENSE:
             # After defense statement, transition to final vote
             print("Defense concluded, moving to final vote...")
             env.step_phase()
        elif current_phase == GamePhase.DAY_DISCUSSION:
              # If the action was successful and didn't trigger an immediate phase change (like accusation)
              # advance_turn was likely called within process_player_action or should be called if needed.
              # Check if discussion should end naturally (e.g., everyone passed)
              if env._check_discussion_end():
                   print("Discussion round ended.")
                   env._transition_to_voting() # Check if this leads to game end
                   if env.state.game_over: break
        # No explicit advancement needed for other handled phases (they transition within their logic)


    # --- End of Simulation ---
    print("\n" + "="*15 + " Game Over " + "="*15)
    if step_count >= max_steps:
        print(f"Simulation ended: Reached max steps ({max_steps}).")
        env.state.log_message("system", f"Game ended due to reaching max steps ({max_steps}).", msg_type="system")
        # Ensure game_over is set if not already
        if not env.state.game_over:
            env.state.game_over = True
            env.state.phase = GamePhase.GAME_OVER
            env.state.winner = None # Mark as undecided/timeout

    winner_faction = env.state.winner
    winner_str = winner_faction.value.upper() if winner_faction else "UNDECIDED (Timeout or Draw)"
    print(f"Winner: {winner_str}")
    print(f"Ended on Day {env.state.day_count}, Phase: {env.state.phase.name}")
    print(f"Final Roles: {env.state.final_player_roles}")
    print(f"Final Alive: {sorted(list(env.state.alive_players))}")

    # Generate and return summary
    summary = log_game_summary(env.state, token_tracker)
    # summary["action_log"] = action_log # Optionally include detailed action log

    print(f"--- Simulation Complete [ID: {sim_id}] ---")
    return summary


def run_multiple_simulations(num_games: int = 3, # Reduced default for quicker testing
                             config_path: Optional[str] = None, # Make config path optional
                             base_config: Optional[Dict] = None, # Allow passing config directly
                             save_dir: str = "output/sim_results"):
    """Runs multiple simulations and saves the results."""

    if not config_path and not base_config:
         print("Error: Must provide either a config_path or a base_config dictionary.")
         return

    if config_path and not base_config:
         print(f"Loading base configuration from: {config_path}")
         base_game_config = load_config_from_file(config_path)
         if not base_game_config: # Fallback if loading fails
              print("Using minimal default config for testing.")
              base_game_config = {
                   "roles": [{"name": f"P{i}", "role": "Villager"} for i in range(1, 6)],
                   "agent_mapping": {f"P{i}": "rule" for i in range(1, 6)},
                   "max_steps": 50
              }
    elif base_config:
         print("Using provided base configuration dictionary.")
         base_game_config = base_config
    else: # Both provided, maybe prefer direct config?
         print("Using provided base configuration dictionary (config_path ignored).")
         base_game_config = base_config


    # Ensure save directory exists
    try:
        os.makedirs(save_dir, exist_ok=True)
        log_file = os.path.join(save_dir, "mafia_games_log.jsonl")
        print(f"Results will be saved to: {log_file}")
    except OSError as e:
        print(f"Error creating save directory '{save_dir}': {e}. Results will not be saved.")
        log_file = None


    game_results = []
    error_count = 0

    print(f"\nRunning {num_games} Mafia simulations...")
    for i in tqdm(range(num_games), desc="Simulating Games"):
        game_id = f"sim_{i+1}_{str(uuid.uuid4())[:8]}" # Unique ID for each game run
        current_game_config = {**base_game_config, "game_id": game_id} # Add unique ID
        result = {}
        try:
            # Run the simulation - agent_config is now part of game_config
            result = run_simulation(game_config=current_game_config)
            result["status"] = "completed"
            game_results.append(result)
        except Exception as e:
            print(f"\n!!!!!! Critical Error during simulation {game_id} !!!!!!")
            import traceback
            traceback.print_exc() # Print detailed traceback
            print(f"Error: {e}")
            result = {"game_id": game_id, "status": "error", "error_message": str(e)}
            error_count += 1
            # Optionally save error info
            game_results.append(result) # Add error result to list

        # Save result incrementally to log file if possible
        if log_file:
            try:
                with open(log_file, "a", encoding="utf-8") as f:
                    # Convert Enum members in winner field to string before saving
                    if 'winner' in result and isinstance(result['winner'], Faction):
                         result['winner'] = result['winner'].value
                    json.dump(result, f)
                    f.write("\n")
            except IOError as e:
                 print(f"\nWarning: Could not write to log file {log_file}: {e}")
                 # Maybe disable logging for future iterations if it keeps failing?
                 # log_file = None
            except TypeError as e:
                 print(f"\nWarning: Could not serialize result for {game_id} to JSON: {e}")
                 print(f"Problematic result data: {result}")


    # --- Final Summary ---
    completed_games = len(game_results) - error_count
    print(f"\n=== Multi-Simulation Complete ===")
    print(f"Total Simulations Run: {num_games}")
    print(f"Successfully Completed: {completed_games}")
    print(f"Errors Encountered: {error_count}")
    if log_file and completed_games > 0:
        print(f"Results saved to: {log_file}")
    elif log_file and error_count > 0:
         print(f"Error details saved to: {log_file}")


    # Optional: Basic aggregate stats
    if completed_games > 0:
        winners = [g["winner"] for g in game_results if g.get("status") == "completed" and g.get("winner")]
        if winners:
            from collections import Counter
            win_counts = Counter(winners)
            print("\nFaction Win Distribution:")
            for faction, count in win_counts.items():
                 print(f"  - {faction}: {count} wins ({count/completed_games:.1%})")

def main():
    """Main entry point for running simulations."""
    # Example: Run 3 games using a configuration file
    # Ensure 'config/default_game.json' exists or change the path
    # config_file = "config/default_game.json"
    # if not os.path.exists(config_file):
    #     print(f"Warning: Config file '{config_file}' not found. Create one or use direct config.")
    #     # Minimal config if file doesn't exist
    #     default_config = {
    #         "roles": [{"name": "P1", "role": "Cop", "agent_mapping": "llm"}, {"name": "P2", "role": "Goon", "agent_mapping":"rule"}],
    #         "llm_agent_config": {"backend_type": "dummy"},
    #         "max_steps": 30
    #     }
    #     run_multiple_simulations(num_games=2, base_config=default_config, save_dir="output/test_dummy_sims")
    # else:
    #      run_multiple_simulations(num_games=3, config_path=config_file, save_dir="output/default_sims")

    # Example: Run directly with a config dictionary
    print("\nRunning simulation with direct config...")
    direct_config = {
            "roles": [
                {"name": "Alice",   "role": "Cop"},
                {"name": "Bob",     "role": "Doctor"},
                {"name": "Charlie", "role": "Villager"},
                {"name": "David",   "role": "Villager"},
                {"name": "Eve",     "role": "Villager"},
                {"name": "Heidi",   "role": "Godfather"},
                {"name": "Ivan",    "role": "Goon"},
                {"name": "Judy",    "role": "Goon"}
            ],
            "agent_mapping": { # Make Alice (Cop) and Heidi (GF) LLMs, others rules
                "Alice": "llm", "Bob": "rule", "Charlie": "rule", "David": "rule",
                "Eve": "rule", "Heidi": "llm", "Ivan": "rule", "Judy": "rule"
            },
            "llm_agent_config": { # Config for ALL LLM agents in this game
                 "backend_type": "dummy", # Change to "openai", "local_api" etc.
                 "model_identifier": "dummy-model",
                 #"api_key_env_var": "OPENAI_API_KEY", # If using OpenAI
                 #"local_api_endpoint": "http://localhost:11434/v1/chat/completions", # If using Ollama
                 "use_cot": False, # Enable Chain-of-Thought?
                 "generation_params": {"temperature": 0.6, "max_tokens": 200}
            },
             "rule_agent_strategy": { # Config for ALL Rule agents
                  "always_accuse": False, # Make rules less aggressive
                  "always_vote_guilty": False,
                  "always_vote_innocent": False,
             },
            "max_steps": 100,
            "lynch_defense_enabled": True,
            "cop_speaks_first": True,
        }
    run_multiple_simulations(num_games=1, base_config=direct_config, save_dir="output/direct_config_sim")


if __name__ == "__main__":
    main()