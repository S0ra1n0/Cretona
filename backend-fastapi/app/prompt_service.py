from __future__ import annotations

import httpx

from app.config import Settings
from app.schemas import PromptEnhanceRequest, PromptEnhanceResponse


class PromptEnhancer:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    async def enhance(self, request: PromptEnhanceRequest) -> PromptEnhanceResponse:
        original = request.prompt.strip()
        if self.settings.prompt_llm_provider == "ollama":
            enhanced = await self._try_ollama(original, request.aspect_ratio)
            if enhanced:
                return PromptEnhanceResponse(
                    originalPrompt=original,
                    enhancedPrompt=enhanced,
                    provider="ollama",
                    usedFallback=False,
                )

        return PromptEnhanceResponse(
            originalPrompt=original,
            enhancedPrompt=self._deterministic(original, request.aspect_ratio),
            provider="deterministic",
            usedFallback=True,
        )

    async def _try_ollama(self, prompt: str, aspect_ratio: str) -> str | None:
        instruction = (
            "Rewrite the user's idea as one concise English prompt for an AI video model. "
            "Include subject, action, environment, camera movement, lighting, and style. "
            f"Target aspect ratio {aspect_ratio}. Return only the rewritten prompt.\n\n"
            f"User idea: {prompt}"
        )
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.ollama_timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    f"{self.settings.ollama_base_url.rstrip('/')}/api/generate",
                    json={
                        "model": self.settings.ollama_model,
                        "prompt": instruction,
                        "stream": False,
                        # This laptop has only 16 GB RAM. Release the model after
                        # every request so prompt enhancement cannot starve the
                        # separate video worker.
                        "keep_alive": 0,
                        "options": {
                            "num_ctx": self.settings.ollama_num_ctx,
                            "num_predict": self.settings.ollama_num_predict,
                            "temperature": self.settings.ollama_temperature,
                        },
                    },
                )
                response.raise_for_status()
                content = response.json().get("response")
                if isinstance(content, str) and content.strip():
                    return content.strip()[:1000]
        except (httpx.HTTPError, ValueError, TypeError):
            return None
        return None

    @classmethod
    def _deterministic(cls, prompt: str, aspect_ratio: str) -> str:
        translated = cls._expand_vietnamese_if_present(prompt)
        return (
            f"Cinematic {aspect_ratio} video of {translated}. Clear subject motion, coherent "
            "environment, smooth camera movement, natural lighting, consistent details, "
            "high visual quality, no text or watermark."
        )[:1000]

    @staticmethod
    def _expand_vietnamese_if_present(prompt: str) -> str:
        lowered = prompt.lower()
        replacements = [
            ("con mèo", "a graceful agile cat"),
            ("mèo", "a cute cinematic cat"),
            ("con chó", "a playful faithful dog"),
            ("chó", "a dog"),
            ("rồng", "a majestic mystical dragon with glowing scales"),
            ("hoàng hôn", "a dramatic golden hour sunset over the horizon"),
            ("bình minh", "a serene golden sunrise with soft morning mist"),
            ("thành phố", "a vibrant futuristic cyberpunk metropolis at night"),
            ("biển", "a crystal-clear turquoise ocean with rolling waves"),
            ("núi", "majestic snow-capped mountain peaks"),
            ("hoa", "blooming vibrant exotic flowers"),
            ("mưa", "cinematic gentle rain with reflective glistening streets"),
            ("vũ trụ", "deep outer space with colorful glowing nebulae and stars"),
            ("cô gái", "a beautiful elegant young woman with expressive eyes"),
            ("chàng trai", "a handsome young man"),
            ("xe hơi", "a sleek aerodynamic modern supercar cruising"),
        ]
        result = prompt
        for vn, en in replacements:
            if vn in lowered:
                # Replace case-insensitively
                import re

                result = re.sub(re.escape(vn), en, result, flags=re.IGNORECASE)
        return result
