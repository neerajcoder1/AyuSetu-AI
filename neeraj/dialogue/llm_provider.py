from typing import Protocol, Optional
import os
from openai import OpenAI

class LLMProvider(Protocol):
    """
    Provider-agnostic interface for generating text.
    Can be backed by OpenAI, Groq, Ollama, etc.
    """
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        ...

class OpenAICompatibleProvider(LLMProvider):
    """
    Uses the standard `openai` python package.
    By swapping the base_url, this can point to vLLM, Ollama, Groq, or OpenAI.
    """
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: str = "gpt-4o-mini"):
        # We require an api key to init the client, but fallback to "dummy" for testing/mocking
        key = api_key or os.environ.get("LLM_API_KEY", "dummy")
        self.client = OpenAI(
            api_key=key,
            base_url=base_url or os.environ.get("LLM_BASE_URL")
        )
        self.model = model

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        # If using dummy key in testing, return a deterministic mock
        if self.client.api_key == "dummy":
            return f"[Mocked LLM Response for: {user_prompt.splitlines()[0]}]"
            
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            return f"[LLM Error: {str(e)}]"
