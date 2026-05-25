"""
AI Genre Classification service using local Ollama.

Classifies tracks by sending metadata context (artist, album, title, filename,
directory path, existing tags, MIK key) to a local Ollama model and requesting
structured genre labels with confidence scores.

No audio analysis is performed — genre is inferred purely from metadata signals.
BPM / key / energy analysis is handled externally by Mixed In Key.
"""
import asyncio
import json
import re
from typing import Optional, List, Dict, Any, Tuple

from loguru import logger

try:
    import ollama as ollama_sdk
except ImportError:
    ollama_sdk = None


# ---------------------------------------------------------------------------
# Genre taxonomy — canonical genres the model should choose from
# ---------------------------------------------------------------------------

GENRE_TAXONOMY = [
    # Electronic
    "House", "Deep House", "Tech House", "Progressive House", "Electro House",
    "Acid House", "Afro House", "Melodic House",
    "Techno", "Minimal Techno", "Industrial Techno", "Melodic Techno",
    "Trance", "Progressive Trance", "Uplifting Trance", "Psy Trance", "Vocal Trance",
    "Drum and Bass", "Liquid DnB", "Jungle", "Neurofunk",
    "Dubstep", "Riddim", "Brostep",
    "Ambient", "Downtempo", "Chillout", "Lo-Fi",
    "Breakbeat", "UK Garage", "2-Step",
    "Hardstyle", "Hardcore", "Gabber",
    "IDM", "Glitch", "Experimental Electronic",
    "Synthwave", "Retrowave", "Vaporwave",
    "Electronica", "Electro", "EBM",
    "Disco", "Nu-Disco", "Italo Disco",
    # Pop / Rock
    "Pop", "Synth Pop", "Indie Pop", "K-Pop", "J-Pop", "Power Pop",
    "Rock", "Alternative Rock", "Indie Rock", "Classic Rock", "Hard Rock",
    "Punk", "Pop Punk", "Post-Punk",
    "Metal", "Heavy Metal", "Death Metal", "Black Metal", "Prog Metal",
    "Grunge", "Emo", "Shoegaze", "Post-Rock",
    # Hip-Hop / R&B
    "Hip-Hop", "Trap", "Boom Bap", "Lo-Fi Hip-Hop", "Conscious Hip-Hop",
    "R&B", "Neo-Soul", "Contemporary R&B", "Soul", "Funk",
    # Other
    "Jazz", "Smooth Jazz", "Acid Jazz", "Jazz Fusion",
    "Blues", "Country", "Folk", "Americana",
    "Reggae", "Dub", "Dancehall", "Ska",
    "Latin", "Reggaeton", "Salsa", "Bossa Nova", "Cumbia",
    "Classical", "Orchestral", "Soundtrack", "New Age",
    "World", "Afrobeat", "Afropop",
    "Gospel", "Christian",
    "Podcast", "Spoken Word", "Audiobook", "Comedy",
]

# Flatten for prompt
_GENRE_LIST_STR = ", ".join(GENRE_TAXONOMY)

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

SINGLE_TRACK_PROMPT = """You are an expert music genre classifier. Given the metadata for an audio track, determine the most accurate genre label(s).

RULES:
0. If "External enrichment" is present, weight it heavily — these tags come from real listener data (MusicBrainz, Last.fm), audio fingerprinting (AcoustID), and web search. They override speculation from filenames.
1. Return 1-3 genre labels, ordered by relevance.
2. Choose ONLY from this genre list: {genres}
3. If none of the genres fit well, pick the closest match.
4. The musical key (from Mixed In Key) can provide hints — e.g., minor keys are more common in techno/trance, major keys in pop/house.
5. The directory path may contain genre hints (e.g., "/music/Trance/Armin van Buuren/").
6. Consider the artist's known primary genre when available.

Track metadata:
- Filename: {filename}
- Directory: {directory}
- Title: {title}
- Artist: {artist}
- Album: {album}
- Current Genre Tag: {current_genre}
- Musical Key (from Mixed In Key): {mik_key}
- Year: {year}

External enrichment:
{enrichment}

Expert analysis (from reasoning model):
{expert_analysis}

Respond with ONLY valid JSON, no other text:
{{"genres": ["Primary Genre", "Secondary Genre"], "confidence": 85, "reasoning": "brief explanation"}}"""

BATCH_PROMPT_HEADER = """You are an expert music genre classifier. I will give you a batch of tracks. For each track, determine 1-3 genre labels.

Choose ONLY from: {genres}

Consider, in priority order:
  1. The "expert_analysis" block on each track (if present) — a reasoning model has already weighed the signals. Treat this as the strongest authority.
  2. The "enrichment" block on each track — verified tags from MusicBrainz, Last.fm, AcoustID, and web search.
  3. The artist's known genre.
  4. Directory structure hints, musical key, album context, and filename patterns.

Tracks:
{tracks_json}

Respond with ONLY a JSON array, one object per track in the same order:
[{{"track_id": 1, "genres": ["Genre1", "Genre2"], "confidence": 85, "reasoning": "brief"}}]"""


INVESTIGATOR_PROMPT = """You are an expert music analyst. Analyze this track's genre using all available signals. Think step-by-step but be concise.

Track:
- Artist: {artist}
- Title: {title}
- Album: {album}
- Year: {year}
- Filename: {filename}
- Directory path: {directory}
- Current genre tag: {current_genre}
- Musical key (Mixed In Key): {mik_key}

External enrichment data (from MusicBrainz, Last.fm, AcoustID, web search):
{enrichment}

Analyze in 3-6 sentences:
1. What is the artist's primary genre / style / scene?
2. What do the enrichment tags strongly suggest? Note the most-voted tags.
3. Era / regional / production cues (year, label, key).
4. Conflicting signals — which source is most authoritative and why?
5. Final recommendation: 1-3 candidate genre labels with brief justification.

Output plain text only. Do NOT output JSON. Do NOT include <think> tags in your final answer."""


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------

class GenreClassifier:
    """Classify track genres using a local Ollama model."""

    def __init__(
        self,
        model: str = "qwen3:32b",
        host: str = "http://localhost:11434",
        timeout: float = 120.0,
        reasoning_model: str = "deepseek-r1:latest",
        two_pass_enabled: bool = False,
    ):
        self.model = model
        self.host = host
        self.timeout = timeout
        self.reasoning_model = reasoning_model
        self.two_pass_enabled = two_pass_enabled
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if ollama_sdk is None:
                raise RuntimeError(
                    "ollama Python package is not installed. "
                    "Run: pip install ollama"
                )
            self._client = ollama_sdk.Client(host=self.host)
        return self._client

    def _chat_no_think(self, **kwargs) -> Any:
        """Call client.chat() with think=False if supported.

        Qwen3/DeepSeek-R1 family emit <think>...</think> reasoning tokens that
        consume the num_predict budget and leave content empty when format=json
        is also requested. Passing think=False disables reasoning. Older ollama
        SDK / server versions don't support the kwarg, so we fall back gracefully
        and also append a /no_think instruction to the last user message.
        """
        try:
            return self.client.chat(model=self.model, think=False, **kwargs)
        except TypeError:
            # SDK doesn't support think kwarg — append soft hint and retry
            msgs = kwargs.get("messages") or []
            if msgs and isinstance(msgs, list) and msgs[-1].get("role") == "user":
                content = msgs[-1].get("content", "")
                if "/no_think" not in content:
                    msgs[-1] = {**msgs[-1], "content": content + "\n\n/no_think"}
            return self.client.chat(model=self.model, **kwargs)

    async def _investigate(self, track_metadata: Dict[str, Any], enrichment_block: str) -> str:
        """Pass 1 of two-pass classification.

        Calls the reasoning model (deepseek-r1 by default) with think=True to
        produce a structured analysis of the track's genre. Output is plain text
        that the classifier model uses as a strong prior in pass 2.
        """
        if ollama_sdk is None:
            return "(reasoning model unavailable: ollama SDK not installed)"

        prompt = INVESTIGATOR_PROMPT.format(
            artist=track_metadata.get("artist", "Unknown"),
            title=track_metadata.get("title", "Unknown"),
            album=track_metadata.get("album", ""),
            year=track_metadata.get("year", ""),
            filename=track_metadata.get("filename", "Unknown"),
            directory=track_metadata.get("directory", ""),
            current_genre=track_metadata.get("genre", ""),
            mik_key=track_metadata.get("mik_key", ""),
            enrichment=enrichment_block,
        )

        def _call():
            try:
                return self.client.chat(
                    model=self.reasoning_model,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.4, "num_predict": 2048},
                    think=True,
                )
            except TypeError:
                # SDK without think kwarg — reasoning still happens inline
                return self.client.chat(
                    model=self.reasoning_model,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.4, "num_predict": 2048},
                )

        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(None, _call)
            content = ""
            if hasattr(resp, "message") and resp.message:
                content = getattr(resp.message, "content", "") or ""
            elif isinstance(resp, dict):
                content = resp.get("message", {}).get("content", "") or ""
            # Strip stray <think>...</think> blocks that some servers leave inline
            content = re.sub(r"<think>[\s\S]*?</think>", "", content, flags=re.IGNORECASE).strip()
            content = re.sub(r"<think>[\s\S]*$", "", content, flags=re.IGNORECASE).strip()
            return content or "(reasoning model returned no analysis)"
        except Exception as e:
            logger.warning(f"Investigator pass failed ({self.reasoning_model}): {e}")
            return f"(reasoning model error: {e})"

    # ------------------------------------------------------------------
    # Health / status
    # ------------------------------------------------------------------

    async def check_status(self) -> Dict[str, Any]:
        """Check Ollama connectivity and whether the configured model is available."""
        result = {
            "available": False,
            "host": self.host,
            "model": self.model,
            "model_loaded": False,
            "models": [],
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

            result["available"] = True
            result["models"] = model_names
            # Exact-match check so the UI can detect misconfigured model names
            result["model_loaded"] = self.model in model_names
        except Exception as e:
            result["error"] = str(e)
            logger.warning(f"Ollama not reachable at {self.host}: {e}")

        return result

    # ------------------------------------------------------------------
    # Single-track classification
    # ------------------------------------------------------------------

    async def classify_track(self, track_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classify a single track's genre.

        Args:
            track_metadata: dict with keys: filename, directory, title, artist,
                            album, genre (current), mik_key, year, track_id,
                            and optionally fingerprint_raw + duration for
                            AcoustID enrichment.

        Returns:
            dict with: genres (list[str]), confidence (int 0-100), reasoning (str)
        """
        # --- Enrichment: pull authoritative external metadata first ---
        enrichment_block = "(enrichment disabled)"
        try:
            from backend.services.enrichment import enrich_track, load_enrichment_settings
            cfg = await load_enrichment_settings()
            if cfg.get("enabled", True):
                bundle = await enrich_track(
                    artist=track_metadata.get("artist") or "",
                    title=track_metadata.get("title") or "",
                    fingerprint=track_metadata.get("fingerprint_raw"),
                    duration=track_metadata.get("duration"),
                    lastfm_api_key=cfg.get("lastfm_api_key", ""),
                    acoustid_api_key=cfg.get("acoustid_api_key", ""),
                    searxng_url=cfg.get("searxng_url", ""),
                    discogs_token=cfg.get("discogs_token", ""),
                    spotify_client_id=cfg.get("spotify_client_id", ""),
                    spotify_client_secret=cfg.get("spotify_client_secret", ""),
                    use_web_search=cfg.get("use_web_search", True),
                )
                enrichment_block = bundle.to_prompt_block()
        except Exception as e:
            logger.warning(f"Enrichment lookup failed (continuing without): {e}")
            enrichment_block = f"(enrichment unavailable: {e})"

        # --- Pass 1: investigator (reasoning model) ---
        expert_analysis = "(two-pass disabled)"
        if self.two_pass_enabled:
            expert_analysis = await self._investigate(track_metadata, enrichment_block)

        prompt = SINGLE_TRACK_PROMPT.format(
            genres=_GENRE_LIST_STR,
            filename=track_metadata.get("filename", "Unknown"),
            directory=track_metadata.get("directory", ""),
            title=track_metadata.get("title", "Unknown"),
            artist=track_metadata.get("artist", "Unknown"),
            album=track_metadata.get("album", ""),
            current_genre=track_metadata.get("genre", ""),
            mik_key=track_metadata.get("mik_key", ""),
            year=track_metadata.get("year", ""),
            enrichment=enrichment_block,
            expert_analysis=expert_analysis,
        )

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._chat_no_think(
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.3, "num_predict": 512},
                    format="json",
                ),
            )

            content = response.get("message", {}).get("content", "")
            if hasattr(response, "message"):
                content = response.message.content

            return self._parse_single_response(content, track_metadata)

        except Exception as e:
            logger.error(f"Genre classification failed for {track_metadata.get('filename')}: {e}")
            return {
                "genres": [],
                "confidence": 0,
                "reasoning": f"Classification error: {e}",
                "error": str(e),
            }

    # ------------------------------------------------------------------
    # Batch classification
    # ------------------------------------------------------------------

    async def classify_batch(
        self,
        tracks: List[Dict[str, Any]],
        batch_size: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Classify genres for a batch of tracks.
        Splits into sub-batches to stay within context window limits.

        Returns list of result dicts in same order as input.
        """
        all_results = []

        # Load enrichment config once for the whole batch
        enrichment_cfg: Optional[Dict[str, Any]] = None
        try:
            from backend.services.enrichment import load_enrichment_settings
            enrichment_cfg = await load_enrichment_settings()
            if not enrichment_cfg.get("enabled", True):
                enrichment_cfg = None
        except Exception as e:
            logger.warning(f"Could not load enrichment settings: {e}")
            enrichment_cfg = None

        for i in range(0, len(tracks), batch_size):
            batch = tracks[i : i + batch_size]

            # Enrich the whole batch in parallel before prompting
            enrichments: List[str] = ["(enrichment disabled)"] * len(batch)
            if enrichment_cfg:
                try:
                    from backend.services.enrichment import enrich_track
                    bundles = await asyncio.gather(*[
                        enrich_track(
                            artist=t.get("artist") or "",
                            title=t.get("title") or "",
                            fingerprint=t.get("fingerprint_raw"),
                            duration=t.get("duration"),
                            lastfm_api_key=enrichment_cfg.get("lastfm_api_key", ""),
                            acoustid_api_key=enrichment_cfg.get("acoustid_api_key", ""),
                            searxng_url=enrichment_cfg.get("searxng_url", ""),
                            discogs_token=enrichment_cfg.get("discogs_token", ""),
                            spotify_client_id=enrichment_cfg.get("spotify_client_id", ""),
                            spotify_client_secret=enrichment_cfg.get("spotify_client_secret", ""),
                            use_web_search=enrichment_cfg.get("use_web_search", True),
                        )
                        for t in batch
                    ], return_exceptions=True)
                    enrichments = [
                        b.to_prompt_block() if hasattr(b, "to_prompt_block")
                        else f"(enrichment error: {b})"
                        for b in bundles
                    ]
                except Exception as e:
                    logger.warning(f"Batch enrichment failed: {e}")

            # Build a compact JSON representation for the prompt
            tracks_for_prompt = []
            # Pass 1: run investigator per-track in parallel (if two-pass enabled)
            analyses: List[str] = ["(two-pass disabled)"] * len(batch)
            if self.two_pass_enabled:
                try:
                    analyses_raw = await asyncio.gather(*[
                        self._investigate(t, enrichments[idx])
                        for idx, t in enumerate(batch)
                    ], return_exceptions=True)
                    analyses = [
                        a if isinstance(a, str) else f"(reasoning error: {a})"
                        for a in analyses_raw
                    ]
                except Exception as e:
                    logger.warning(f"Batch investigator pass failed: {e}")

            for idx, t in enumerate(batch):
                tracks_for_prompt.append({
                    "track_id": idx + 1,
                    "filename": t.get("filename", ""),
                    "directory": t.get("directory", ""),
                    "title": t.get("title", ""),
                    "artist": t.get("artist", ""),
                    "album": t.get("album", ""),
                    "current_genre": t.get("genre", ""),
                    "mik_key": t.get("mik_key", ""),
                    "year": t.get("year", ""),
                    "enrichment": enrichments[idx],
                    "expert_analysis": analyses[idx],
                })

            prompt = BATCH_PROMPT_HEADER.format(
                genres=_GENRE_LIST_STR,
                tracks_json=json.dumps(tracks_for_prompt, indent=2),
            )

            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda p=prompt: self._chat_no_think(
                        messages=[{"role": "user", "content": p}],
                        options={"temperature": 0.3, "num_predict": 4096},
                        format="json",
                    ),
                )

                content = response.get("message", {}).get("content", "")
                if hasattr(response, "message"):
                    content = response.message.content

                batch_results = self._parse_batch_response(content, batch)
                all_results.extend(batch_results)

            except Exception as e:
                logger.error(f"Batch genre classification error (batch {i}): {e}")
                # Fall back to individual classification
                for t in batch:
                    result = await self.classify_track(t)
                    all_results.append(result)

        return all_results

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_single_response(
        self, content: str, track_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Parse the LLM's JSON response for a single track."""
        fallback = {
            "genres": [],
            "confidence": 0,
            "reasoning": "Could not parse model response",
        }

        try:
            data = self._extract_json(content)
            if not data:
                logger.warning(f"No JSON in response for {track_metadata.get('filename')}: {content[:200]}")
                return fallback

            genres = data.get("genres", [])
            # Validate genres against taxonomy
            validated = [g for g in genres if self._match_genre(g)]
            if not validated and genres:
                # Try fuzzy matching
                validated = [self._closest_genre(g) for g in genres]
                validated = [g for g in validated if g]

            return {
                "genres": validated[:3],
                "confidence": min(max(int(data.get("confidence", 50)), 0), 100),
                "reasoning": data.get("reasoning", ""),
            }

        except Exception as e:
            logger.warning(f"Error parsing genre response: {e}")
            return fallback

    def _parse_batch_response(
        self, content: str, tracks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Parse the LLM's JSON response for a batch of tracks."""
        fallback_list = [
            {"genres": [], "confidence": 0, "reasoning": "Parse error"}
            for _ in tracks
        ]

        try:
            data = self._extract_json(content)
            if not data:
                logger.warning(f"No JSON in batch response: {content[:300]}")
                return fallback_list

            # Response might be a list or a dict with a list inside
            items = data if isinstance(data, list) else data.get("results", data.get("tracks", []))
            if not isinstance(items, list):
                return fallback_list

            results = []
            for i, track in enumerate(tracks):
                if i < len(items):
                    item = items[i]
                    genres = item.get("genres", [])
                    validated = [g for g in genres if self._match_genre(g)]
                    if not validated and genres:
                        validated = [self._closest_genre(g) for g in genres]
                        validated = [g for g in validated if g]

                    results.append({
                        "genres": validated[:3],
                        "confidence": min(max(int(item.get("confidence", 50)), 0), 100),
                        "reasoning": item.get("reasoning", ""),
                    })
                else:
                    results.append({"genres": [], "confidence": 0, "reasoning": "Missing from batch response"})

            return results

        except Exception as e:
            logger.warning(f"Error parsing batch genre response: {e}")
            return fallback_list

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json(text: str) -> Any:
        """Extract JSON object or array from text that may contain markdown fences
        or reasoning tokens (<think>...</think>) from Qwen3/DeepSeek-R1 models."""
        text = text.strip()

        # Strip <think>...</think> blocks emitted by reasoning models
        text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()
        # If unclosed <think> at end (truncated by num_predict), drop everything after it
        text = re.sub(r"<think>[\s\S]*$", "", text, flags=re.IGNORECASE).strip()

        # Remove markdown code fences
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

        if not text:
            return None

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object or array in the text
        for pattern in [r"\{[\s\S]*\}", r"\[[\s\S]*\]"]:
            match = re.search(pattern, text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    continue

        return None

    def _match_genre(self, genre: str) -> bool:
        """Check if genre matches any in the taxonomy (case-insensitive)."""
        genre_lower = genre.lower().strip()
        return any(g.lower() == genre_lower for g in GENRE_TAXONOMY)

    def _closest_genre(self, genre: str) -> Optional[str]:
        """Find closest matching genre from taxonomy using simple string matching."""
        genre_lower = genre.lower().strip()

        # Exact match
        for g in GENRE_TAXONOMY:
            if g.lower() == genre_lower:
                return g

        # Substring match
        for g in GENRE_TAXONOMY:
            if genre_lower in g.lower() or g.lower() in genre_lower:
                return g

        # Word overlap
        genre_words = set(genre_lower.split())
        best_match = None
        best_overlap = 0
        for g in GENRE_TAXONOMY:
            g_words = set(g.lower().split())
            overlap = len(genre_words & g_words)
            if overlap > best_overlap:
                best_overlap = overlap
                best_match = g

        return best_match if best_overlap > 0 else None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_classifier: Optional[GenreClassifier] = None


def get_genre_classifier() -> GenreClassifier:
    """Get or create the genre classifier singleton."""
    global _classifier
    if _classifier is None:
        _classifier = GenreClassifier()
    return _classifier


async def init_genre_classifier_from_db():
    """Load AI model/host from saved settings (called at app startup).
    
    If the saved/default model is not installed in Ollama, auto-pick the first
    available installed model so genre classification works out of the box.
    """
    global _classifier
    try:
        from backend.services.database import load_saved_settings_db, save_settings_db
        saved = await load_saved_settings_db()
        model = saved.get("ai_model", "qwen3:32b")
        host = saved.get("ai_host", "http://localhost:11434")
        reasoning_model = saved.get("reasoning_model", "deepseek-r1:latest")
        two_pass_enabled = bool(saved.get("two_pass_enabled", False))
        _classifier = GenreClassifier(
            model=model,
            host=host,
            reasoning_model=reasoning_model,
            two_pass_enabled=two_pass_enabled,
        )
        logger.info(
            f"AI classifier initialized: model={model}, host={host}, "
            f"two_pass={two_pass_enabled}, reasoning={reasoning_model}"
        )

        # If the configured model isn't actually installed, pick a fallback
        try:
            installed = await list_available_models(host=host)
        except Exception:
            installed = []
        if installed and model not in installed:
            # Prefer larger/general-purpose models first
            preference = [
                "qwen3:32b", "qwen3.6:latest", "qwen2.5:32b", "qwen2.5:14b",
                "qwen2.5:7b", "llama3.1:70b", "llama3.1:8b", "deepseek-r1:latest",
            ]
            fallback = next((m for m in preference if m in installed), installed[0])
            logger.warning(
                f"Configured Ollama model '{model}' is not installed. "
                f"Falling back to '{fallback}'. Installed: {installed}"
            )
            _classifier = GenreClassifier(model=fallback, host=host)
            try:
                saved["ai_model"] = fallback
                saved["ai_host"] = host
                await save_settings_db(saved)
            except Exception as e:
                logger.warning(f"Could not persist AI fallback model: {e}")
    except Exception as e:
        logger.warning(f"Could not load AI settings from DB, using defaults: {e}")
        _classifier = GenreClassifier()


async def update_classifier_settings(
    model: Optional[str] = None,
    host: Optional[str] = None,
    reasoning_model: Optional[str] = None,
    two_pass_enabled: Optional[bool] = None,
) -> GenreClassifier:
    """Update classifier settings and persist to DB."""
    global _classifier
    current = get_genre_classifier()
    new_model = model or current.model
    new_host = host or current.host
    new_reasoning = reasoning_model or current.reasoning_model
    new_two_pass = (
        current.two_pass_enabled if two_pass_enabled is None else bool(two_pass_enabled)
    )
    _classifier = GenreClassifier(
        model=new_model,
        host=new_host,
        reasoning_model=new_reasoning,
        two_pass_enabled=new_two_pass,
    )
    # Persist to DB
    try:
        from backend.services.database import save_settings_db, load_saved_settings_db
        current_settings = await load_saved_settings_db()
        current_settings["ai_model"] = new_model
        current_settings["ai_host"] = new_host
        current_settings["reasoning_model"] = new_reasoning
        current_settings["two_pass_enabled"] = new_two_pass
        await save_settings_db(current_settings)
        logger.info(
            f"AI settings saved: model={new_model}, host={new_host}, "
            f"two_pass={new_two_pass}, reasoning={new_reasoning}"
        )
    except Exception as e:
        logger.warning(f"Could not persist AI settings: {e}")
    return _classifier


async def unload_current_model(host: Optional[str] = None, model: Optional[str] = None) -> bool:
    """Force Ollama to unload the model from memory by sending keep_alive=0.

    Ollama keeps models resident in VRAM/RAM for ~5 minutes after the last
    request by default. Sending an empty request with keep_alive=0 evicts it
    immediately, freeing memory after the user stops a batch scan.
    """
    if ollama_sdk is None:
        return False
    try:
        classifier = get_genre_classifier()
        h = host or classifier.host
        m = model or classifier.model
        client = ollama_sdk.AsyncClient(host=h)
        # An empty prompt with keep_alive=0 tells Ollama to unload the model
        await client.generate(model=m, prompt="", keep_alive=0)
        logger.info(f"Unloaded Ollama model '{m}' from memory")
        return True
    except Exception as e:
        logger.warning(f"Failed to unload Ollama model: {e}")
        return False


async def list_available_models(host: Optional[str] = None) -> List[str]:
    """List models installed in Ollama."""
    if ollama_sdk is None:
        return []
    try:
        h = host or get_genre_classifier().host
        client = ollama_sdk.AsyncClient(host=h)
        resp = await client.list()
        # Newer ollama SDK returns ListResponse with .models = [Model(...)]
        # Older versions return dicts. Handle both.
        models = getattr(resp, "models", None)
        if models is None and isinstance(resp, dict):
            models = resp.get("models", [])
        if not models:
            return []
        names = []
        for m in models:
            name = getattr(m, "model", None) or getattr(m, "name", None)
            if name is None and isinstance(m, dict):
                name = m.get("model") or m.get("name")
            if name:
                names.append(name)
        return names
    except Exception as e:
        logger.warning(f"Failed to list Ollama models: {e}")
        return []
