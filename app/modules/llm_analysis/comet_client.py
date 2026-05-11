from typing import Any

import httpx

from app.core.config import get_settings


class CometAPIClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.comet_api_key
        self.model = settings.comet_model_default
        self.base_url = "https://api.cometapi.com"
        self._timeout = httpx.Timeout(30.0)

    async def analyze_text(self, prompt: str) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("COMET_API_KEY is required")

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(f"{self.base_url}/v1/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

