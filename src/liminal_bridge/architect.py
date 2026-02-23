import os
import json
from typing import Dict, Any, Optional

class Architect:
    def __init__(self, api_key: Optional[str] = None, model: str = None):
        self.api_key = api_key or os.getenv("DUCKY_API_KEY")
        self.model = model or os.getenv("DUCKY_MODEL", "gpt-4o")
        self.provider = "openai"
        self.client = None
        self.google_model = None

        if self.api_key:
            # Simple heuristic to detect provider
            if self.model.startswith("gemini") or (self.api_key.startswith("AIza") and len(self.api_key) > 30):
                self.provider = "google"
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=self.api_key)
                    self.google_model = genai.GenerativeModel(self.model)
                except ImportError:
                    print("Warning: google-generativeai package not installed. Architect disabled for Gemini.")
            else:
                try:
                    from openai import AsyncOpenAI
                    self.client = AsyncOpenAI(api_key=self.api_key)
                except ImportError:
                    print("Warning: openai package not installed. Architect disabled for OpenAI.")

    async def consult(self, swarm_state: Dict[str, Any]) -> str:
        """
        Consults the external 'Rubber Ducky' (Architect) to refine the plan.
        """
        prompt = f"""
        You are the System Architect for a swarm of autonomous coding agents (Jules).
        Your goal is to prevent hallucinations and coordination failures by providing a clear, high-level plan.

        Current Swarm State (Liminal Space):
        {json.dumps(swarm_state, indent=2)}

        Task:
        1. Analyze the current state of thoughts and locks.
        2. Identify any conflicts or missing tasks.
        3. Generate a refined Backlog of the next 3-5 critical tasks.
        4. Output the result as a concise JSON object with a 'backlog' key.
        """

        if self.provider == "google":
            return await self._consult_google(prompt)
        else:
            return await self._consult_openai(prompt)

    async def _consult_openai(self, prompt: str) -> str:
        if not self.client:
             return "Architect not configured (missing API key or openai package)."

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a precise technical architect."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Error consulting architect (OpenAI): {str(e)}"

    async def _consult_google(self, prompt: str) -> str:
        if not self.google_model:
            return "Architect not configured (missing API key or google-generativeai package)."

        try:
            # Gemini doesn't support system messages exactly the same way in all versions,
            # but usually we can just prepend it or use the config.
            # Also, JSON mode needs specific config.

            # Note: synchronous call in async wrapper might block, but acceptable for this scope.
            # Ideally use async generation if available in SDK, currently it is async in some versions.

            response = await self.google_model.generate_content_async(
                contents=[prompt],
                generation_config={"response_mime_type": "application/json"}
            )
            return response.text
        except Exception as e:
            return f"Error consulting architect (Gemini): {str(e)}"
