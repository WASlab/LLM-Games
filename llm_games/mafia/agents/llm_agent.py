# === mafia/agents/llm_agent.py ===

import json
import os # Added for API key loading
from typing import Dict, Any, Optional, List

# Import necessary components from the project
from llm_games.mafia.agents.base_agent import BaseAgent
from llm_games.mafia.enums import GamePhase # Needed for phase-specific prompts

# Placeholder for actual LLM API clients (e.g., OpenAI, Anthropic, local vLLM/Ollama)
# You would replace these comments with actual imports and client initialization
# Example using OpenAI:
from openai import OpenAI
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Example using a local model via requests:
# import requests
# LOCAL_MODEL_ENDPOINT = "http://localhost:8000/v1/completions" # Example for vLLM/Ollama OpenAI-compatible API

class LLMAgent(BaseAgent):
    """
    An LLM-powered agent that interacts with the environment using various model backends.
    Includes enhanced prompting based on game state and phase.
    """
    def __init__(self,
                 name: str,
                 # model_backend is now simplified, actual logic moved to act/helper
                 config: Optional[Dict[str, Any]] = None):
        """
        :param name: Agent/player name
        :param config: Configuration dictionary containing:
                       - model_identifier: (e.g., "gpt-4", "local_ollama_model")
                       - backend_type: ("openai", "anthropic", "local_api", "dummy")
                       - system_prompt_base: Base system prompt (optional, built dynamically if not provided)
                       - api_key_env_var: Environment variable name for API key (e.g., "OPENAI_API_KEY")
                       - local_api_endpoint: URL for local model inference endpoint
                       - generation_params: Dict of parameters for LLM generation (temperature, max_tokens, etc.)
                       - use_cot: Boolean flag to enable Chain-of-Thought prompting hints
        """
        super().__init__(name)
        self.config = config or {}
        self.last_observation: Optional[Dict[str, Any]] = None
        self.model_identifier = self.config.get("model_identifier", "gpt-3.5-turbo") # Default model
        self.backend_type = self.config.get("backend_type", "dummy") # Default to dummy
        self.api_key_env_var = self.config.get("api_key_env_var")
        self.local_api_endpoint = self.config.get("local_api_endpoint")
        self.generation_params = self.config.get("generation_params", {"temperature": 0.7, "max_tokens": 150})
        self.use_cot = self.config.get("use_cot", False) # Default CoT to false

        # --- Initialize Model Backend Client ---
        # This part needs to be adapted based on the chosen backend_type
        self.model_client = None
        if self.backend_type == "openai":
            # Example: Load OpenAI client
            # api_key = os.environ.get(self.api_key_env_var)
            # if not api_key:
            #     print(f"Warning: OpenAI API key not found in env var '{self.api_key_env_var}' for agent {self.name}")
            # else:
            #     # self.model_client = OpenAI(api_key=api_key)
            #     print(f"OpenAI client initialized for {self.name}")
            print(f"Placeholder: Initialize OpenAI client for {self.name} using model {self.model_identifier}")
        elif self.backend_type == "anthropic":
            # Example: Load Anthropic client
            # api_key = os.environ.get(self.api_key_env_var)
            # if not api_key:
            #     print(f"Warning: Anthropic API key not found in env var '{self.api_key_env_var}' for agent {self.name}")
            # else:
            #     # import anthropic
            #     # self.model_client = anthropic.Anthropic(api_key=api_key)
            #     print(f"Anthropic client initialized for {self.name}")
            print(f"Placeholder: Initialize Anthropic client for {self.name} using model {self.model_identifier}")
        elif self.backend_type == "local_api":
            if not self.local_api_endpoint:
                 print(f"Warning: Local API endpoint not configured for agent {self.name}")
            else:
                 print(f"Placeholder: Using local API endpoint {self.local_api_endpoint} for {self.name}")
        elif self.backend_type == "dummy":
            print(f"Agent {self.name} is using a dummy backend.")
        else:
            print(f"Warning: Unknown backend type '{self.backend_type}' for agent {self.name}. Using dummy.")
            self.backend_type = "dummy"
        # --- End Backend Initialization ---


    def observe(self, observation: Dict[str, Any]):
        """Stores the latest observation from the environment."""
        self.last_observation = observation

    def act(self) -> Dict[str, Any]:
        """Generates an action based on the last observation using the configured LLM backend."""
        if not self.last_observation:
            # Should not happen in normal flow, but good practice
            return {"action": "pass", "content": "No observation received yet."}

        # Build the prompt based on the current game phase and observation
        prompt = self.build_prompt(self.last_observation) # Now uses the enhanced build_prompt

        raw_output = ""
        try:
            # --- Call Appropriate Model Backend ---
            if self.backend_type == "openai" and self.model_client:
                # response = self.model_client.chat.completions.create(
                #     model=self.model_identifier,
                #     messages=[{"role": "system", "content": prompt}], # Simplification, consider history
                #     **self.generation_params
                # )
                # raw_output = response.choices[0].message.content
                raw_output = '{"action": "speak", "content": "Placeholder OpenAI response."}' # Placeholder
            elif self.backend_type == "anthropic" and self.model_client:
                 # response = self.model_client.messages.create(
                 #    model=self.model_identifier,
                 #    system=prompt, # Anthropic uses 'system' parameter
                 #    messages=[{"role": "user", "content": "What is your action?"}], # Example user message
                 #    **self.generation_params
                 # )
                 # raw_output = response.content[0].text
                 raw_output = '{"action": "vote", "target": "Bob", "vote_type": "final_guilty"}' # Placeholder
            elif self.backend_type == "local_api" and self.local_api_endpoint:
                # Example using requests for an OpenAI-compatible local API
                # headers = {"Content-Type": "application/json"}
                # if self.api_key_env_var: # If local API needs a key (e.g., LM Studio)
                #      headers["Authorization"] = f"Bearer {os.environ.get(self.api_key_env_var, 'dummy-key')}"
                # payload = {
                #     "model": self.model_identifier,
                #     "messages": [{"role": "system", "content": prompt}],
                #     **self.generation_params
                # }
                # response = requests.post(self.local_api_endpoint, headers=headers, json=payload)
                # response.raise_for_status() # Raise exception for bad status codes
                # raw_output = response.json()["choices"][0]["message"]["content"]
                 raw_output = '{"action": "night_action", "target": "Charlie"}' # Placeholder
            else: # Dummy backend
                raw_output = '{"action": "pass", "content": "Dummy agent takes a pass."}'
             # --- End Backend Call ---

        except Exception as e:
            print(f"Error during model inference for agent {self.name} (Backend: {self.backend_type}): {e}")
            # Fallback to a safe action like "pass" on error
            raw_output = '{"action": "pass", "content": "Error during generation."}'

        # Parse the LLM's raw output into a structured action dictionary
        action = self.parse_action(raw_output)
        return action

    def _format_player_list(self, obs: Dict[str, Any]) -> List[str]:
        """Formats the player list with status tags based on observation."""
        player_list_str = []
        all_players = obs.get("player_list", []) # Use the pre-formatted list from game_state
        
        # Fallback if player_list isn't provided directly
        if not all_players:
             alive = obs.get("alive_players", [])
             dead = obs.get("dead_players", [])
             on_trial = obs.get("player_on_trial")
             # Note: Mafia visibility would require more logic here if building from scratch
             for p_name in sorted(list(set(alive + dead))):
                  tags = []
                  if p_name in dead: tags.append("DEAD")
                  if p_name == on_trial: tags.append("On Trial")
                  # Mafia tag would need player object access - simplified here
                  status_str = f" [{', '.join(tags)}]" if tags else ""
                  player_list_str.append(f"{p_name}{status_str}")
        else:
            player_list_str = all_players # Use the already formatted list

        return player_list_str


    def build_prompt(self, obs: Dict[str, Any]) -> str:
        """
        Builds a comprehensive system prompt for the LLM agent based on the game state.
        Introduces the game, summarizes role/faction, describes phase logic,
        includes player lists, messages, and memory.
        """
        lines = []

        # --- Game Introduction & Role ---
        lines.append("=== Welcome to the Game of Mafia ===")
        lines.append(f"You are Player: {self.name}")
        lines.append(f"Your Role: {obs.get('role', 'Unknown Role')}")
        lines.append(f"Your Faction: {obs.get('faction', 'Unknown Faction').upper()}")
        lines.append(f"Your Objective: {obs.get('role_description', 'Win with your faction.')}")
        if obs.get('faction', '') == 'mafia' and obs.get('mafia_members', []):
             lines.append(f"Your Mafia Teammates (Alive): {', '.join(obs.get('mafia_members', []))}")

        # --- Current Game State ---
        lines.append("\n=== Current Game State ===")
        current_phase_str = obs.get('phase', 'unknown').replace('_', ' ').title()
        lines.append(f"Current Phase: {current_phase_str} (Day {obs.get('day', 0)})")
        if obs.get('is_current_turn', False):
             lines.append("It is currently YOUR TURN to act.")
        else:
             lines.append(f"It is currently {obs.get('current_player_turn', 'Someone')}'s turn.")

        # --- Player List ---
        lines.append("\n=== Players ===")
        player_list_formatted = self._format_player_list(obs)
        lines.extend([f"- {p}" for p in player_list_formatted])
        if obs.get('player_on_trial'):
            lines.append(f"Player on Trial: {obs.get('player_on_trial')}")


        # --- Recent Messages ---
        lines.append("\n=== Recent Messages (Last 20) ===")
        messages = obs.get("messages", [])
        if messages:
             lines.extend([f"- {msg}" for msg in messages])
        else:
             lines.append("- No messages yet in this phase.")

        # --- Memory / Known Information ---
        # Display investigation results, role peeks, etc.
        memory = obs.get("memory", [])
        if memory:
             lines.append("\n=== Your Private Memory ===")
             for mem_item in memory:
                  if mem_item.get("type") == "investigation_result":
                       lines.append(f"- Day {mem_item.get('day')}: Investigated {mem_item.get('target')} - Faction: {mem_item.get('result').upper()}")
                  elif mem_item.get("type") == "role_peek":
                        lines.append(f"- Day {mem_item.get('day')}: Saw {mem_item.get('target')}'s role - Role: {mem_item.get('role')}")
                  # Add other memory types as needed
                  else:
                       lines.append(f"- {mem_item}") # Generic display

        # --- Phase-Specific Instructions & Action Format ---
        lines.append("\n=== Your Task ===")
        current_phase_enum = GamePhase(obs.get('phase')) if obs.get('phase') in GamePhase._value2member_map_ else None

        # Use helper for phase-specific instructions
        phase_instructions = self._get_phase_instructions(current_phase_enum, obs)
        lines.extend(phase_instructions)

        # Add CoT hint if enabled
        if self.use_cot:
             lines.append("\nThink step-by-step about your goal, the current situation, potential threats/allies, and your best action. Then, provide your final action in the specified JSON format.")

        lines.append("\nOutput ONLY the JSON for your chosen action. Do not include any other text, explanation, or reasoning outside the JSON structure.")
        lines.append('Example JSON format: {"action": "ACTION_TYPE", "target": "PLAYER_NAME", "content": "Your message here", "vote_type": "GUILTY/INNOCENT"}')
        lines.append("Include ONLY the necessary fields for your chosen action type.")

        return "\n".join(lines)


    def _get_phase_instructions(self, phase: Optional[GamePhase], obs: Dict[str, Any]) -> List[str]:
        """ Provides specific instructions based on the current game phase. """
        instructions = []
        alive_players = obs.get("alive_players", [])
        valid_targets = [p for p in alive_players if p != self.name] # General valid targets

        if phase == GamePhase.NIGHT:
            instructions.append("It is Night. Choose your night action if applicable.")
            if obs.get('can_act_tonight', False):
                instructions.append("Select your target from the list of alive players.")
                instructions.append(f"Valid Targets: {', '.join(valid_targets) or 'None'}")
                instructions.append('Action JSON: {"action": "night_action", "target": "PLAYER_NAME"}')
            else:
                instructions.append("You have no action this night.")
                instructions.append('Action JSON: {"action": "pass"}')
        elif phase == GamePhase.DAY_DISCUSSION:
            instructions.append("It is the Day Discussion phase.")
            if obs.get('is_current_turn', False):
                 if obs.get("can_speak", True):
                     instructions.append("It's your turn to speak, accuse, question, or pass.")
                     instructions.append(" - To speak: {'action': 'speak', 'content': 'Your message...'}")
                     # Allow accusation only if no one is on trial and not Day 0
                     if not obs.get("player_on_trial") and obs.get("day", 0) > 0:
                         instructions.append(" - To accuse: {'action': 'accuse', 'target': 'PLAYER_NAME'}")
                     instructions.append(" - To question: {'action': 'question', 'target': 'PLAYER_NAME', 'content': 'Your question...'}")
                     # Add other actions like predict, whisper if implemented fully
                     instructions.append(" - To pass: {'action': 'pass'}")
                     instructions.append(f"Valid Targets for accuse/question: {', '.join(valid_targets) or 'None'}")
                 else:
                     instructions.append("You cannot speak this turn (e.g., blackmailed). You must pass.")
                     instructions.append('Action JSON: {"action": "pass"}')
            else:
                 instructions.append("It is not your turn. You cannot act now.")
                 # Technically agent shouldn't be asked to act if not its turn, but good to handle.
                 instructions.append('Action JSON: {"action": "pass"}') # Default safe action
        elif phase == GamePhase.VOTING:
             # This phase might be skipped or merged depending on config, but handle it
             instructions.append("It is the initial Voting Phase.")
             if obs.get("player_on_trial"):
                 instructions.append(f"You are voting on whether to proceed to a final trial for {obs.get('player_on_trial')}.")
                 instructions.append(" - To vote for trial: {'action': 'vote', 'target': 'PLAYER_ON_TRIAL_NAME'}") # Target is the accused
                 instructions.append(" - To skip/abstain: {'action': 'skip'}")
             else:
                 instructions.append("No one is currently on trial. This phase should transition.")
                 instructions.append('Action JSON: {"action": "pass"}')
        elif phase == GamePhase.DEFENSE:
             instructions.append("It is the Defense Phase.")
             if obs.get("player_on_trial") == self.name:
                 instructions.append("You are on trial! Speak in your defense.")
                 instructions.append('Action JSON: {"action": "speak", "content": "Your defense statement..."}')
             else:
                 instructions.append(f"{obs.get('player_on_trial')} is giving their defense. Wait for the Final Vote.")
                 instructions.append('Action JSON: {"action": "pass"}') # Cannot act if not on trial
        elif phase == GamePhase.FINAL_VOTE:
             instructions.append("It is the Final Vote Phase.")
             accused = obs.get('player_on_trial')
             if accused:
                instructions.append(f"Vote whether {accused} is GUILTY or INNOCENT.")
                instructions.append(" - Vote Guilty: {'action': 'vote', 'vote_type': 'final_guilty'}")
                instructions.append(" - Vote Innocent: {'action': 'vote', 'vote_type': 'final_innocent'}")
                # Optional Abstain:
                # instructions.append(" - Abstain: {'action': 'vote', 'vote_type': 'abstain'}")
             else:
                instructions.append("Error: Final Vote phase but no player on trial.")
                instructions.append('Action JSON: {"action": "pass"}')
        elif phase == GamePhase.GAME_OVER:
             instructions.append("The game is over.")
             winner = obs.get("winner")
             instructions.append(f"Winner: {winner.upper() if winner else 'Undecided'}")
             instructions.append('Action JSON: {"action": "pass"}') # No actions possible
        else: # Fallback
             instructions.append("Unknown game phase. Please pass.")
             instructions.append('Action JSON: {"action": "pass"}')

        return instructions


    def parse_action(self, response: str) -> Dict[str, Any]:
        """
        Attempts to parse the LLM's JSON output.
        Handles potential errors and defaults to a safe 'pass' action.
        """
        try:
            # Clean up potential markdown code blocks or leading/trailing text
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif response.startswith("{") and response.endswith("}"):
                 response = response.strip()
            else:
                 # Try to find JSON within the response if it's not clean
                 start = response.find('{')
                 end = response.rfind('}')
                 if start != -1 and end != -1 and end > start:
                      response = response[start:end+1]
                 else:
                      # If still no valid JSON structure found, raise error
                      raise json.JSONDecodeError("No valid JSON object found in the response.", response, 0)


            # Parse the cleaned JSON string
            data = json.loads(response)

            # Basic validation: 'action' field is mandatory
            if "action" not in data or not isinstance(data["action"], str):
                print(f"Warning: LLM response for {self.name} missing 'action' field or invalid type. Raw: {response}")
                return {"action": "pass", "content": "Invalid action format received."}

            # Sanitize action dictionary (e.g., remove unexpected fields if necessary)
            # valid_keys = {"action", "target", "content", "vote_type"}
            # action_data = {k: v for k, v in data.items() if k in valid_keys}

            return data # Return the parsed (and potentially sanitized) action

        except json.JSONDecodeError as e:
            print(f"Error parsing JSON response for agent {self.name}: {e}")
            print(f"Raw response: {response}")
            # Fallback to pass on JSON errors
            return {"action": "pass", "content": "Failed to parse response."}
        except Exception as e: # Catch other potential errors
             print(f"Unexpected error parsing action for {self.name}: {e}")
             print(f"Raw response: {response}")
             return {"action": "pass", "content": "Unexpected error processing response."}

    def reset(self):
        """Resets the agent's state for a new game."""
        self.last_observation = None
        # Potentially clear conversation history if maintained internally
        print(f"Agent {self.name} reset for new game.")