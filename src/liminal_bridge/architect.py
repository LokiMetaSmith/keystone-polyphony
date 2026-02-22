import os
import json
from typing import Dict, Any, Optional

class Architect:
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o"):
        self.api_key = api_key or os.getenv("DUCKY_API_KEY")
        self.model = model or os.getenv("DUCKY_MODEL", "gpt-4o")
        self.client = None

        if self.api_key:
            try:
                from openai import AsyncOpenAI
                self.client = AsyncOpenAI(api_key=self.api_key)
            except ImportError:
                print("Warning: openai package not installed. Architect will be disabled.")

    async def consult(self, swarm_state: Dict[str, Any]) -> str:
        """
        Consults the external 'Rubber Ducky' (Architect) to refine the plan.
        """
        if not self.client:
            return "Architect not configured (missing API key or openai package)."

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
            return f"Error consulting architect: {str(e)}"
