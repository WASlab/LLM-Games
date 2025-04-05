import os
import json
import uuid
from typing import Dict, List, Optional

from tqdm import tqdm

from llm_games.mafia.environment import MafiaEnvironment
from llm_games.mafia.player import Player
from llm_games.mafia.mechanics.roles import get_role_class
from llm_games.mafia.agents.rule_agent import RuleAgent
from llm_games.mafia.agents.llm_agent import LLMAgent
from llm_games.mafia.enums import GamePhase


class TokenTracker:
    def __init__(self):
        self.usage = {}

    def update(self, *args, **kwargs):
        pass

    def to_dict(self) -> Dict[str, Dict[str, int]]:
        return self.usage


def load_config_from_file(path: str) -> Dict:
    print(f"Attempting to load config from {path} (stub).")
    return {}


def create_players_from_config(config: Dict) -> List[Player]:
    players = []
    roles_config = config.get("roles", [])
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
        role_instance = RoleClass()
        player = Player(name=name, role=role_instance)

        agent_type = config.get("agent_mapping", {}).get(name, "rule").lower()
        if agent_type == "llm":
            model_name = config.get("llm_config", {}).get("model", "gpt-3.5-turbo")
            system_prompt = (
                f"You are {name}, playing Mafia as {role_instance.name}. "
                f"{role_instance.get_role_description()}"
            )

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
            strategy = config.get("agent_strategy", {})
            agent = RuleAgent(name=name, role=role_instance.name, strategy=strategy)
            print(f"Assigning RuleAgent to {name} ({role_name})")

        player.agent = agent
        players.append(player)

    return players


def log_game_summary(game_state) -> Dict:
    return {
        "game_id": game_state.game_id,
        "winner": game_state.winner.value if game_state.winner else None,
        "final_roles": game_state.final_player_roles,
        "day_count": game_state.day_count
    }


def run_simulation(game_config: Dict, agent_config: Dict) -> Dict:
    print(f"\n--- Starting Simulation Game ID: {game_config.get('game_id', 'N/A')} ---")
    combined_config = {**game_config, "agents": agent_config}

    players = create_players_from_config(combined_config)
    env = MafiaEnvironment(players=players, config=combined_config)

    if env.state.phase != GamePhase.NIGHT:
        env.state.phase = GamePhase.NIGHT
    print("Game begins at Night (Day 0). Agents may converse/pass; initial kills occur here if applicable.")

    token_tracker = TokenTracker()
    max_steps = combined_config.get("max_steps", 100)
    step_count = 0

    while not env.state.game_over and step_count < max_steps:
        step_count += 1
        print(f"\n=== [Step {step_count}] Day {env.state.day_count}, Phase: {env.state.phase.name}, Turn: {env.state.turn_number_in_phase} ===")

        current_phase = env.state.phase
        current_player_name = env.get_current_player_name()

        # Final vote is non-turn-based: every alive player votes
        if current_phase == GamePhase.FINAL_VOTE:
            for name in env.state.alive_players:
                player = env.state.get_player(name)
                if not player or not player.alive:
                    continue
                obs = env.get_observation(name)
                player.agent.observe(obs)
                act = player.agent.act()
                print(f"{name} votes: {act}")
                env.process_player_action(name, act)
            env.step_phase()
            continue

        # Other phases
        if not current_player_name:
            print("No current player; environment resolving phase...")
            env.step_phase()
            continue

        player = env.state.get_player(current_player_name)
        if not player or not player.alive:
            print(f"Skipping turn for {current_player_name} (dead or invalid).")
            env.advance_turn()
            continue

        observation = env.get_observation(current_player_name)
        agent = player.agent
        agent.observe(observation)
        agent_action = agent.act()
        print(f"{current_player_name} (role={player.role.name}) chooses: {agent_action}")

        success = env.process_player_action(current_player_name, agent_action)
        if not success:
            print(f"Action failed or was invalid: {agent_action}")
        else:
            env.advance_turn()

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
            "llm_config": {"model": "gpt-3.5-turbo"},
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
            print(f"\n!!!!!! Error during simulation {game_id} !!!!!!")
            print(f"Error: {e}")
            error_info = {"game_id": game_id, "status": "error", "error_message": str(e)}
            with open(log_file, "a", encoding="utf-8") as f:
                json.dump(error_info, f)
                f.write("\n")

    print(f"\n=== Simulations Complete ===\nSaved {len(game_results)} game logs to {log_file}")


def main():
    run_multiple_simulations(num_games=3)


if __name__ == "__main__":
    main()
