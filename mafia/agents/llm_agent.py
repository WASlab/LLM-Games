# mafia/agents/llm_agent.py
import os
import openai
from mafia.agents.base import BaseAgent
from mafia.prompts.mafia_template import format_prompt, parse_response

class LLMAPIClientAgent(BaseAgent):
    def __init__(self, name: str, model: str = "gpt-4", system_prompt: str = None):
        super().__init__(name)
        self.model = model
        self.system_prompt = system_prompt or "You are playing the game Mafia. Reason carefully."
        self.client = openai.ChatCompletion  # Can be monkey-patched for DeepSeek etc.

    def act(self, observation: dict) -> dict:
        prompt = format_prompt(self.name, observation)
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt}
        ]
        response = self.client.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
        )
        raw = response.choices[0].message.content.strip()
        return parse_response(raw)
