from typing import Protocol, Optional
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

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
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        load_dotenv()
        key = api_key or os.environ.get("LLM_API_KEY", "dummy")
        url = base_url or os.environ.get("LLM_BASE_URL")
        
        self.client = OpenAI(
            api_key=key,
            base_url=url
        )
        
        if model:
            self.model = model
        elif os.environ.get("LLM_MODEL"):
            self.model = os.environ.get("LLM_MODEL")
        elif url and "groq.com" in url:
            self.model = "groq/compound-mini"
        else:
            self.model = "gpt-4o-mini"

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
