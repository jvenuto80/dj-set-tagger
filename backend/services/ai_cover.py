"""
AI-powered cover art assessment using Ollama vision models.

Uses a vision-capable model (llava, llava:13b, etc.) to evaluate whether
embedded cover art is correct, high-quality, and matches the track metadata.
"""
import asyncio
import base64
import json
import re
from typing import Optional, Dict, Any, List

from loguru import logger

try:
    import ollama as ollama_sdk
except ImportError:
    ollama_sdk = None


ASSESS_PROMPT = """You are a music library cover art quality inspector. Analyze this album/single cover art image and the track metadata.

Track metadata:
- Title: {title}
- Artist: {artist}
- Album: {album}
- Genre: {genre}

Evaluate:
1. Is this a real album/single cover (not a placeholder, screenshot, or random image)?
2. Does it look professional (proper artwork, not a phone photo or low-quality scan)?
3. Does it seem to match the artist/album (if recognizable)?
4. Is the image quality acceptable (not blurry, pixelated, or cropped badly)?

Respond with ONLY valid JSON:
{{"is_valid_cover": true, "quality_score": 85, "matches_metadata": true, "issues": [], "description": "Brief description of what the image shows"}}

Where:
- is_valid_cover: true if this is actual album artwork
- quality_score: 0-100 overall quality rating
- matches_metadata: true if the image appears to match the artist/album
- issues: list of any problems found (e.g. "blurry", "placeholder image", "wrong artist")
- description: 1-sentence description of what you see"""


class CoverArtAssessor:
    """Assess cover art quality using Ollama vision models."""

    def __init__(
        self,
        model: str = "llava:13b",
        host: str = "http://localhost:11434",
    ):
        self.model = model
        self.host = host
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if ollama_sdk is None:
                raise RuntimeError("ollama package not installed")
            self._client = ollama_sdk.Client(host=self.host)
        return self._client

    async def check_status(self) -> Dict[str, Any]:
        """Check if the vision model is available."""
        result = {
            "available": False,
            "model": self.model,
            "host": self.host,
            "error": None,
        }
        try:
            loop = asyncio.get_event_loop()
            models_resp = await loop.run_in_executor(None, self.client.list)
            model_names = []
            if hasattr(models_resp, "models"):
                model_names = [m.model for m in models_resp.models]
            elif isinstance(models_resp, dict):
                model_names = [m.get("name", "") for m in models_resp.get("models", [])]

            result["available"] = any(
                self.model in name or name.startswith(self.model.split(":")[0])
                for name in model_names
            )
            if not result["available"]:
                result["error"] = f"Model {self.model} not found. Available: {model_names}"
        except Exception as e:
            result["error"] = str(e)

        return result

    async def assess(
        self,
        image_data: bytes,
        title: str = "",
        artist: str = "",
        album: str = "",
        genre: str = "",
    ) -> Dict[str, Any]:
        """
        Assess cover art quality using the vision model.

        Args:
            image_data: Raw image bytes (JPEG/PNG)
            title/artist/album/genre: Track metadata for context

        Returns:
            {is_valid_cover, quality_score, matches_metadata, issues, description}
        """
        prompt = ASSESS_PROMPT.format(
            title=title or "Unknown",
            artist=artist or "Unknown",
            album=album or "Unknown",
            genre=genre or "Unknown",
        )

        b64_image = base64.b64encode(image_data).decode("utf-8")

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.chat(
                    model=self.model,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                            "images": [b64_image],
                        }
                    ],
                    options={"temperature": 0.2, "num_predict": 512},
                ),
            )

            content = response.get("message", {}).get("content", "")
            if hasattr(response, "message"):
                content = response.message.content

            return self._parse_response(content)

        except Exception as e:
            logger.error(f"Cover art assessment failed: {e}")
            return {
                "is_valid_cover": None,
                "quality_score": 0,
                "matches_metadata": None,
                "issues": [f"Assessment error: {e}"],
                "description": "",
                "error": str(e),
            }

    def _parse_response(self, content: str) -> Dict[str, Any]:
        """Parse the vision model's JSON response."""
        fallback = {
            "is_valid_cover": None,
            "quality_score": 0,
            "matches_metadata": None,
            "issues": ["Could not parse response"],
            "description": "",
        }

        try:
            text = content.strip()
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            text = text.strip()

            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                match = re.search(r"\{[\s\S]*\}", text)
                if match:
                    data = json.loads(match.group())
                else:
                    return fallback

            return {
                "is_valid_cover": data.get("is_valid_cover"),
                "quality_score": min(max(int(data.get("quality_score", 0)), 0), 100),
                "matches_metadata": data.get("matches_metadata"),
                "issues": data.get("issues", []),
                "description": data.get("description", ""),
            }

        except Exception as e:
            logger.warning(f"Error parsing cover assessment: {e}")
            return fallback


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_assessor: Optional[CoverArtAssessor] = None


def get_cover_assessor() -> CoverArtAssessor:
    global _assessor
    if _assessor is None:
        _assessor = CoverArtAssessor()
    return _assessor


async def update_assessor_settings(
    model: Optional[str] = None,
    host: Optional[str] = None,
) -> CoverArtAssessor:
    global _assessor
    current = get_cover_assessor()
    _assessor = CoverArtAssessor(
        model=model or current.model,
        host=host or current.host,
    )
    return _assessor
