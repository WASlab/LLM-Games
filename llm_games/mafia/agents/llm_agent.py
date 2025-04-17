# === mafia/agents/llm_agent.py ===

import json
import os
import re # Import regex for potential future use in parsing, though parsing happens in environment
from typing import Dict, Any, Optional, List

# Import necessary components from the project
from llm_games.mafia.agents.base_agent import BaseAgent
from llm_games.mafia.enums import GamePhase

# --- Dependency Check & Import ---
# Ensure you have installed the necessary libraries:
# pip install google-generativeai python-dotenv
try:
    import google.generativeai as genai
    GOOGLE_GENERATIVEAI_INSTALLED = True
except ImportError:
    GOOGLE_GENERATIVEAI_INSTALLED = False
    print("Warning: 'google-generativeai' library not found. Gemini backend will not work.")
    print("Install it using: pip install google-generativeai")

# Placeholder for other LLM API clients (if needed)
# from openai import OpenAI
# import requests

class LLMAgent(BaseAgent):
    """
    An LLM-powered agent that interacts with the environment using various model backends.
    Outputs actions in a hybrid JSON format:
    - Simple JSON for direct actions (vote, night_action, pass).
    - JSON 'speak' action where the 'content' string can contain
      special tags like <accuse>Target</accuse> or <question>Target</question>.
    """
    def __init__(self,
                 name: str,
                 config: Optional[Dict[str, Any]] = None):
        """
        :param name: Agent/player name
        :param config: Configuration dictionary containing:
                       - model_identifier: (e.g., "gemini-1.5-flash", "gpt-4o")
                       - backend_type: ("gemini", "openai", "anthropic", "local_api", "dummy")
                       - system_prompt_base: Base system prompt (optional, built dynamically if not provided)
                       - api_key_env_var: Environment variable name for API key (e.g., "GEMINI_API_KEY")
                       - local_api_endpoint: URL for local model inference endpoint
                       - generation_params: Dict of parameters for LLM generation (temperature, max_tokens, etc.)
                       - use_cot: Boolean flag to enable Chain-of-Thought prompting hints
        """
        super().__init__(name)
        self.config = config or {}
        self.last_observation: Optional[Dict[str, Any]] = None
        self.model_identifier = self.config.get("model_identifier", "gemini-1.5-flash") # Default model
        self.backend_type = self.config.get("backend_type", "dummy") # Default to dummy
        self.api_key_env_var = self.config.get("api_key_env_var")
        self.local_api_endpoint = self.config.get("local_api_endpoint")
        self.generation_params = self.config.get("generation_params", {"temperature": 0.7}) # Gemini uses safety settings, max_tokens less common directly here
        self.use_cot = self.config.get("use_cot", False)

        # --- Load API Key ---
        self.api_key = None
        if self.api_key_env_var:
            self.api_key = os.environ.get(self.api_key_env_var)
            if not self.api_key:
                print(f"Warning: API key environment variable '{self.api_key_env_var}' not found for agent {self.name}.")

        # --- Initialize Model Backend Client ---
        self.model_client = None # For stateful clients if needed
        self.gemini_model = None # Specific handle for Gemini model

        if self.backend_type == "gemini":
            if not GOOGLE_GENERATIVEAI_INSTALLED:
                print(f"Error: Cannot use Gemini backend for {self.name}. 'google-generativeai' not installed.")
                self.backend_type = "dummy" # Fallback
            elif not self.api_key:
                 print(f"Error: Cannot initialize Gemini client for {self.name}. API key is missing (checked env var: {self.api_key_env_var}).")
                 self.backend_type = "dummy" # Fallback
            else:
                 try:
                     # Configure the Gemini client
                     genai.configure(api_key=self.api_key)
                     # Create the specific model instance
                     gen_config_gemini = genai.types.GenerationConfig(
                         temperature=self.generation_params.get('temperature', 0.7),
                         # max_output_tokens=self.generation_params.get('max_tokens', 250), # Add if needed
                     )
                     self.gemini_model = genai.GenerativeModel(
                         self.model_identifier,
                         generation_config=gen_config_gemini
                         # safety_settings=... # Add safety settings if desired
                     )
                     print(f"Gemini client configured for {self.name} using model {self.model_identifier}")
                 except Exception as e:
                     print(f"Error configuring Gemini client for {self.name}: {e}")
                     self.backend_type = "dummy" # Fallback

        # Add initialization logic for other backends (openai, anthropic, local_api) here
        # using self.api_key or self.local_api_endpoint as needed
        elif self.backend_type != "dummy":
             print(f"Agent {self.name} backend '{self.backend_type}' not fully implemented yet. Using dummy.")
             self.backend_type = "dummy"

        if self.backend_type == "dummy":
            print(f"Agent {self.name} is using a dummy backend.")
        # --- End Backend Initialization ---


    def observe(self, observation: Dict[str, Any]):
        """Stores the latest observation from the environment."""
        self.last_observation = observation

    def act(self) -> Dict[str, Any]:
        """Generates an action based on the last observation using the configured LLM backend."""
        if not self.last_observation:
            return {"action": "pass", "content": "No observation received yet."}

        prompt = self.build_prompt(self.last_observation)
        # print(f"\n--- Agent {self.name} Prompt ---\n{prompt}\n---------------------------\n") # Optional: Debug prompt

        raw_output = ""
        try:
            # --- Call Appropriate Model Backend ---
            if self.backend_type == "gemini" and self.gemini_model:
                # print(f"Sending request to Gemini model: {self.model_identifier} for agent {self.name}...")
                response = self.gemini_model.generate_content(prompt)
                if response.parts:
                     raw_output = response.text
                else:
                     print(f"Warning: Gemini response for {self.name} has no parts. Block reason: {response.prompt_feedback.block_reason}")
                     raw_output = '{"action": "pass", "content": "Generation blocked or empty."}'

            # Add elif blocks here for other backends (openai, anthropic, local_api)
            # elif self.backend_type == "openai" and self.model_client: ...

            else: # Dummy backend
                # Simulate hybrid output for dummy testing if desired
                phase = self.last_observation.get('phase')
                if phase == GamePhase.DAY_DISCUSSION.value and self.last_observation.get('is_current_turn'):
                     dummy_target = next((p for p in self.last_observation.get('alive_players',[]) if p != self.name), None)
                     if dummy_target:
                          raw_output = f'{{"action": "speak", "content": "This is a dummy message. I think <accuse>{dummy_target}</accuse> is suspicious."}}'
                     else:
                          raw_output = '{"action": "speak", "content": "This is a dummy message."}'
                elif phase == GamePhase.NIGHT.value and self.last_observation.get('can_act_tonight'):
                     dummy_target = next((p for p in self.last_observation.get('alive_players',[]) if p != self.name), None)
                     if dummy_target:
                           raw_output = f'{{"action": "night_action", "target": "{dummy_target}"}}'
                     else:
                           raw_output = '{"action": "pass"}' # No target
                elif phase == GamePhase.FINAL_VOTE.value:
                    raw_output = '{"action": "vote", "vote_type": "final_innocent"}'
                else:
                    raw_output = '{"action": "pass", "content": "Dummy agent takes a pass."}'

        except Exception as e:
            print(f"Error during model inference for agent {self.name} (Backend: {self.backend_type}): {e}")
            import traceback
            traceback.print_exc()
            raw_output = '{"action": "pass", "content": "Error during generation."}'

        # print(f"--- Agent {self.name} Raw Response ---\n{raw_output}\n------------------------------\n") # Optional: Debug response

        action = self.parse_action(raw_output)
        return action

    def _format_player_list(self, obs: Dict[str, Any]) -> List[str]:
        """Formats the player list with status tags based on observation."""
        # (This function remains unchanged)
        player_list_str = []
        all_players = obs.get("player_list", [])
        if not all_players:
             alive = obs.get("alive_players", [])
             dead = obs.get("dead_players", [])
             on_trial = obs.get("player_on_trial")
             for p_name in sorted(list(set(alive + dead))):
                  tags = []
                  if p_name in dead: tags.append("DEAD")
                  if p_name == on_trial: tags.append("On Trial")
                  status_str = f" [{', '.join(tags)}]" if tags else ""
                  player_list_str.append(f"{p_name}{status_str}")
        else:
            player_list_str = all_players
        return player_list_str


    def build_prompt(self, obs: Dict[str, Any]) -> str:
        """
        Builds a comprehensive system prompt for the LLM agent based on the game state.
        Instructs the agent to use hybrid JSON + tagged content format.
        """
        lines = []

        # --- Game Introduction & Role ---
        # (This section remains unchanged)
        lines.append("=== Welcome to the Game of Mafia ===")
        lines.append(f"You are Player: {self.name}")
        lines.append(f"Your Role: {obs.get('role', 'Unknown Role')}")
        lines.append(f"Your Faction: {obs.get('faction', 'Unknown Faction').upper()}")
        lines.append(f"Your Objective: {obs.get('role_description', 'Win with your faction.')}")
        if obs.get('faction', '') == 'mafia' and obs.get('mafia_members', []):
             teammates = [p for p in obs.get('mafia_members', []) if p != self.name]
             if teammates: lines.append(f"Your Mafia Teammates (Alive): {', '.join(teammates)}")
             else: lines.append("You are the only remaining Mafia member.")

        # --- Current Game State ---
        # (This section remains unchanged)
        lines.append("\n=== Current Game State ===")
        current_phase_str = obs.get('phase', 'unknown').replace('_', ' ').title()
        lines.append(f"Current Phase: {current_phase_str} (Day {obs.get('day', 0)})")
        if obs.get('is_current_turn', False): lines.append("It is currently YOUR TURN to act.")
        else: lines.append(f"It is currently {obs.get('current_player_turn', 'Someone')}'s turn.")

        # --- Player List ---
        # (This section remains unchanged)
        lines.append("\n=== Players ===")
        player_list_formatted = self._format_player_list(obs)
        lines.extend([f"- {p}" for p in player_list_formatted])
        if obs.get('player_on_trial'): lines.append(f"Player on Trial: {obs.get('player_on_trial')}")

        # --- Recent Messages ---
        # (This section remains unchanged, maybe trim message count more aggressively if prompts get too long)
        num_messages_to_show = 15 # Slightly reduced message history
        lines.append(f"\n=== Recent Messages (Last {num_messages_to_show}) ===")
        messages = obs.get("messages", [])[-num_messages_to_show:]
        if messages: lines.extend([f"- {msg}" for msg in messages])
        else: lines.append("- No messages yet in this phase.")

        # --- Memory / Known Information ---
        # (This section remains unchanged)
        memory = obs.get("memory", [])
        if memory:
             lines.append("\n=== Your Private Memory ===")
             for mem_item in memory:
                  if mem_item.get("type") == "investigation_result": lines.append(f"- Day {mem_item.get('day')}: Investigated {mem_item.get('target')} - Faction: {mem_item.get('result').upper()}")
                  elif mem_item.get("type") == "role_peek": lines.append(f"- Day {mem_item.get('day')}: Saw {mem_item.get('target')}'s role - Role: {mem_item.get('role')}")
                  else: lines.append(f"- {mem_item}")

        # --- Phase-Specific Instructions & Action Format ---
        lines.append("\n=== Your Task ===")
        current_phase_enum = GamePhase(obs.get('phase')) if obs.get('phase') in GamePhase._value2member_map_ else None

        # Use helper for phase-specific instructions (modified helper below)
        phase_instructions = self._get_phase_instructions(current_phase_enum, obs)
        lines.extend(phase_instructions)

        # --- Output Format Definition ---
        lines.append("\n=== Output Format ===")
        lines.append("You MUST output your action as a valid JSON object. ONLY output the JSON, nothing else.")
        lines.append("For most actions (voting, night actions, passing), use simple JSON:")
        lines.append(' - `{"action": "night_action", "target": "PLAYER_NAME"}`')
        lines.append(' - `{"action": "vote", "vote_type": "final_guilty"}`')
        lines.append(' - `{"action": "pass"}`')
        lines.append("\n**For speaking during the day (Discussion or Defense):**")
        lines.append("Use the `speak` action. The `content` field should contain your message.")
        lines.append("You can embed special actions within your speech using tags:")
        lines.append(" - Accuse a player: `<accuse>PLAYER_NAME</accuse>`")
        lines.append(" - Ask a question: `<question>PLAYER_NAME</question> Your question text here.`")
        lines.append("   (The environment will notify the questioned player it's their turn to respond).")
        lines.append(" - Claim a role: `<claim>ROLE_NAME</claim>` (e.g., `<claim>Doctor</claim>`)")
        lines.append("Combine tags and regular text naturally within the `content` string.")

        lines.append("\n**Example `speak` action with tags:**")
        lines.append('`{"action": "speak", "content": "I\'m suspicious of <accuse>Bob</accuse>. <question>Alice</question> can you confirm your role claim of <claim>Doctor</claim>?"}`')

        if self.use_cot:
             lines.append("\n**Reasoning Hint (Chain-of-Thought):**")
             lines.append("Before outputting the final JSON, think step-by-step about your goals, the game state, and why you are choosing this specific action and phrasing. Then, provide ONLY the final JSON object.")

        return "\n".join(lines)


    def _get_phase_instructions(self, phase: Optional[GamePhase], obs: Dict[str, Any]) -> List[str]:
        """ Provides specific instructions based on the current game phase, using the hybrid format. """
        instructions = []
        alive_players = obs.get("alive_players", [])
        valid_targets = sorted([p for p in alive_players if p != self.name]) # General valid targets exclude self

        if phase == GamePhase.NIGHT:
            instructions.append("It is Night. Choose your night action if applicable.")
            if obs.get('can_act_tonight', False):
                night_action_targets = valid_targets # Default
                role = obs.get('role')
                if role == 'Doctor': night_action_targets = sorted(alive_players) # Can target self
                # Add other role-specific target rules here

                instructions.append("Select your target for your night action.")
                instructions.append(f"Valid Targets: {', '.join(night_action_targets) or 'None'}")
                instructions.append('Required Action JSON: `{"action": "night_action", "target": "PLAYER_NAME"}`')
            else:
                instructions.append("You have no action this night or your action was blocked.")
                instructions.append('Required Action JSON: `{"action": "pass"}`')

        elif phase == GamePhase.DAY_DISCUSSION:
            instructions.append("It is the Day Discussion phase.")
            if obs.get('is_current_turn', False):
                 if obs.get("can_speak", True):
                     instructions.append("It's your turn. You can speak, or pass.")
                     instructions.append(" - To speak (and potentially embed actions like accuse/question/claim using tags):")
                     instructions.append('   `{"action": "speak", "content": "Your message with optional <accuse>Target</accuse>, <question>Target</question> Text?, <claim>Role</claim> tags..."}`')
                     instructions.append(f"   (Valid targets for tags: {', '.join(valid_targets) or 'None'})")
                     instructions.append(" - To do nothing this turn:")
                     instructions.append('   `{"action": "pass"}`')
                 else:
                     instructions.append("You cannot speak this turn (e.g., silenced). You must pass.")
                     instructions.append('Required Action JSON: `{"action": "pass"}`')
            else:
                 instructions.append("It is not your turn. Wait for others.")
                 instructions.append('Internal Action: `{"action": "pass"}`') # Agent shouldn't act, but have fallback

        elif phase == GamePhase.VOTING: # Initial Trial Vote (if enabled & separate)
             instructions.append("It is the Trial Voting Phase.")
             accused = obs.get("player_on_trial")
             if accused:
                 instructions.append(f"Vote on whether to put {accused} on final trial.")
                 # Assuming simple vote targetting accused means FOR trial
                 instructions.append(f" - To vote FOR trial: `{{'action': 'vote', 'target': '{accused}'}}`")
                 instructions.append(" - To vote AGAINST trial (or abstain): `{'action': 'skip'}`")
             else:
                 instructions.append("No one is currently nominated for trial.")
                 instructions.append('Required Action JSON: `{"action": "pass"}`')

        elif phase == GamePhase.DEFENSE:
             instructions.append("It is the Defense Phase.")
             accused = obs.get('player_on_trial')
             if accused == self.name:
                 instructions.append("You are on trial! Speak in your defense. You can use <claim>Role</claim> tags.")
                 instructions.append('Required Action JSON: `{"action": "speak", "content": "Your defense statement..."}`')
             elif accused:
                 instructions.append(f"{accused} is giving their defense. Wait for the Final Vote.")
                 instructions.append('Required Action JSON: `{"action": "pass"}`')
             else:
                  instructions.append("Error: Defense phase but no player on trial.")
                  instructions.append('Required Action JSON: `{"action": "pass"}`')

        elif phase == GamePhase.FINAL_VOTE:
             instructions.append("It is the Final Vote Phase.")
             accused = obs.get('player_on_trial')
             can_vote = self.name in alive_players and self.name != accused
             if accused and can_vote:
                instructions.append(f"Vote whether {accused} is GUILTY or INNOCENT.")
                instructions.append(" - Vote Guilty: `{'action': 'vote', 'vote_type': 'final_guilty'}`")
                instructions.append(" - Vote Innocent: `{'action': 'vote', 'vote_type': 'final_innocent'}`")
             elif accused and not can_vote:
                  instructions.append(f"You are {accused} and cannot vote in your own trial. Pass.")
                  instructions.append('Required Action JSON: `{"action": "pass"}`')
             else:
                instructions.append("Error: Final Vote phase but no player on trial or you cannot vote.")
                instructions.append('Required Action JSON: `{"action": "pass"}`')

        elif phase == GamePhase.GAME_OVER:
             instructions.append("The game is over.")
             winner = obs.get("winner")
             instructions.append(f"Winner: {winner.upper() if winner else 'Undecided'}")
             instructions.append('Required Action JSON: `{"action": "pass"}`')
        else: # Fallback
             instructions.append("Unknown or unsupported game phase. Please pass.")
             instructions.append('Required Action JSON: `{"action": "pass"}`')

        return instructions


    def parse_action(self, response: str) -> Dict[str, Any]:
        """
        Attempts to parse the LLM's JSON output.
        Handles potential errors and defaults to a safe 'pass' action.
        The content of the 'content' field is parsed by the environment later.
        """
        # (This function remains largely unchanged - it parses the outer JSON)
        action = {"action": "pass", "content": "Default pass action due to parsing issue."}
        try:
            response_clean = response.strip()
            if response_clean.startswith("```json"): response_clean = response_clean[len("```json"):].strip()
            if response_clean.startswith("```"): response_clean = response_clean[len("```"):].strip()
            if response_clean.endswith("```"): response_clean = response_clean[:-len("```")].strip()

            start = response_clean.find('{')
            end = response_clean.rfind('}')
            if start != -1 and end != -1 and end > start: json_str = response_clean[start:end+1]
            else: json_str = response_clean

            data = json.loads(json_str)

            if isinstance(data, dict) and "action" in data and isinstance(data["action"], str):
                 action = data # Accept the parsed structure
                 # Basic validation for expected fields based on action type could be added here
                 # e.g., if action == 'night_action', check for 'target'
                 if action["action"] == "speak" and "content" not in action:
                      action["content"] = "" # Ensure content field exists for speak actions
            else:
                 print(f"Warning: LLM response for {self.name} missing 'action' field or invalid JSON structure. Raw: {response}")
                 action["content"] = f"Invalid action format received: {response}"

        except json.JSONDecodeError as e:
            print(f"Error parsing JSON response for agent {self.name}: {e}")
            print(f"Raw response snippet: {response[:500]}")
            action["content"] = f"Failed to parse JSON response: {response[:100]}"
        except Exception as e:
             print(f"Unexpected error parsing action for {self.name}: {e}")
             print(f"Raw response snippet: {response[:500]}")
             action["content"] = f"Unexpected error processing response: {e}"

        return action

    def reset(self):
        """Resets the agent's state for a new game."""
        self.last_observation = None
        print(f"Agent {self.name} reset for new game.")