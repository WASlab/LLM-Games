# === mafia/play_test.py ===

# Import the main simulation runner function
from llm_games.mafia.simulation import run_simulation, run_multiple_simulations
import os

# --- Configuration for a Test Game ---
# This game uses 10 players: 1 LLM Cop, 1 LLM Godfather, and 8 RuleAgents.
# RuleAgents have specific strategies to test deception and game mechanics.
test_config = {
    "roles": [
        # Town Roles (7 players)
        {"name": "Alice",   "role": "Cop"},       # LLM Agent
        {"name": "Bob",     "role": "Doctor"},    # Rule Agent
        {"name": "Charlie", "role": "Villager"},  # Rule Agent (Aggressive)
        {"name": "David",   "role": "Villager"},  # Rule Agent
        {"name": "Eve",     "role": "Villager"},  # Rule Agent
        {"name": "Faythe",  "role": "Villager"},  # Rule Agent
        {"name": "Grace",   "role": "Villager"},  # Rule Agent

        # Mafia Roles (3 players)
        {"name": "Heidi",   "role": "Godfather"}, # LLM Agent
        {"name": "Ivan",    "role": "Goon"},      # Rule Agent (Claims Doctor)
        {"name": "Judy",    "role": "Goon"}       # Rule Agent
    ],

    # Agent Mapping: Specify which player gets which agent type
    "agent_mapping": {
        "Alice": "llm",      # Cop is an LLM
        "Bob": "rule",
        "Charlie": "rule",
        "David": "rule",
        "Eve": "rule",
        "Faythe": "rule",
        "Grace": "rule",
        "Heidi": "llm",      # Godfather is an LLM
        "Ivan": "rule",
        "Judy": "rule"
    },

    # --- Agent Configurations ---

    # Global LLM Agent Configuration (applied to Alice and Heidi)
    "llm_agent_config": {
        "backend_type": "dummy",  # IMPORTANT: Change to "openai", "local_api", etc. for real LLMs
        "model_identifier": "dummy-llm",
        # "api_key_env_var": "OPENAI_API_KEY", # Uncomment and set if using OpenAI
        # "local_api_endpoint": "http://localhost:11434/v1/chat/completions", # Example for Ollama
        "use_cot": True,         # Enable Chain-of-Thought prompting for LLMs
        "generation_params": {"temperature": 0.7, "max_tokens": 180}
    },

    # Global Rule Agent Strategy (base strategy for most rule agents)
    "rule_agent_strategy": {
        "always_accuse": False,        # Base rule agents are not overly aggressive
        "always_vote_guilty": False,   # Base rule agents use random voting logic
        "always_vote_innocent": False,
        # Add specific strategies per player below if needed
    },

    # --- Role/Player Specific Agent Overrides ---
    # Example: Override strategy for specific rule agents
    "roles": [
        # ... (previous role definitions) ...
        {"name": "Charlie", "role": "Villager", "agent_strategy": {"always_accuse": True, "always_vote_guilty": True}}, # Aggressive Townie
        {"name": "Ivan",    "role": "Goon",     "agent_strategy": {"claim_role": "Doctor", "always_vote_innocent": True}} # Mafia claiming Doctor
        # Note: The 'claim_role' is a custom strategy key the RuleAgent needs to be programmed to understand.
        #       You'd modify rule_agent.py to handle this. For now, it's illustrative.
    ],


    # --- Environment Configuration ---
    "max_steps": 150,                 # Max simulation steps before timeout
    "lynch_defense_enabled": True,   # Allow accused players to defend themselves
    "cop_speaks_first": False,        # Let discussion order be random initially
    "godfather_detectable": False,   # Godfather appears as Town to Cop
    "doctor_can_self_heal": True,    # Doctor can target themselves

    # Custom game ID for this test run
    "game_id": "test_llm_vs_rules_deception_v1"
}

# --- Main Execution Block ---
if __name__ == "__main__":
    print("=== Running Mafia Test Game: 1 LLM Cop, 1 LLM GF vs. 8 Rule Agents ===")
    print("Rule Agent Strategies:")
    print("  - Charlie (Villager): Always Accuses, Always Votes Guilty")
    print("  - Ivan (Goon): Will attempt to claim Doctor (needs RuleAgent update), Votes Innocent")
    print("  - Others: Standard random/passive rules")
    print("LLM Agents (Alice & Heidi): Using specified backend (currently Dummy) with CoT prompting.")

    # Run a single simulation with the defined test configuration
    # The `agent_config` parameter to run_simulation is less used now,
    # as agent configs are embedded within the main `test_config`.
    summary = run_simulation(game_config=test_config, agent_config=None) # agent_config=None is fine

    print("\n" + "="*20 + " Game Summary " + "="*20)
    if summary.get("status") == "error":
        print("!!! Simulation ended with an error !!!")
        print(f"Error Message: {summary.get('error_message', 'Unknown error')}")
    else:
        # Pretty print the summary dictionary
        for key, value in summary.items():
             if key == "token_usage" and isinstance(value, dict):
                  print(f"{key}:")
                  for agent, tokens in value.items():
                       print(f"  - {agent}: Input={tokens.get('input', 0)}, Output={tokens.get('output', 0)}")
             elif isinstance(value, list):
                  print(f"{key}: {', '.join(map(str, value))}")
             else:
                  print(f"{key}: {value}")

    print("="*54)

    # --- Optional: Run multiple games with this config ---
    # print("\n=== Running 3 simulations with the same test config ===")
    # run_multiple_simulations(
    #     num_games=3,
    #     base_config=test_config, # Use the config directly
    #     save_dir="output/test_llm_vs_rules_multi"
    # )