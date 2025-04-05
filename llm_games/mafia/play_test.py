# play_test.py

from llm_games.mafia.simulation import run_simulation

# Define a configuration with 10 players:
# 7 town players and 3 mafia players.
quick_config = {
    "roles": [
        # Town roles (7 players)
        {"name": "Alice",   "role": "Cop"},
        {"name": "Bob",     "role": "Doctor"},
        {"name": "Charlie", "role": "Villager"},
        {"name": "David",   "role": "Villager"},
        {"name": "Eve",     "role": "Villager"},
        {"name": "Faythe",  "role": "Villager"},
        {"name": "Grace",   "role": "Villager"},
        # Mafia roles (3 players)
        {"name": "Heidi",   "role": "Godfather"},
        {"name": "Ivan",    "role": "Goon"},
        {"name": "Judy",    "role": "Goon"}
    ],
    # Map all agents to the rule-based agent for testing.
    "agent_mapping": {
        "Alice": "rule",
        "Bob": "rule",
        "Charlie": "rule",
        "David": "rule",
        "Eve": "rule",
        "Faythe": "rule",
        "Grace": "rule",
        "Heidi": "rule",
        "Ivan": "rule",
        "Judy": "rule"
    },
    # Set up strategies:
    # For town: always accuse in day discussion and always vote guilty in final vote.
    # For mafia: always perform their night kill action and (optionally) always vote innocent.
    "agent_strategy": {
        # These strategies are read by the RuleAgent in its logic:
        # (The rule agent code checks "always_accuse", "always_vote_guilty", etc.)
        "always_accuse": True,         # All agents will try to accuse when possible.
        "always_vote_guilty": True,     # Town agents vote guilty on trial.
        "always_vote_innocent": True    # Mafia agents vote innocent.
    },
    # Override or add any other configuration options:
    "max_steps": 200,  # Increase max steps if needed to allow game termination.
    # For testing, we force the environment to transition to day immediately:
    #"force_day_on_start": True  
}

# An empty agent config (could be extended later)
agent_config = {}

if __name__ == "__main__":
    print("=== Running a quick Mafia test game with 10 rule agents (7 town, 3 mafia) ===")
    summary = run_simulation(quick_config, agent_config)
    print("\n=== Game Summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")
