"""
Lightweight translation service for product names/descriptions.

Uses simple heuristics to detect English text and translates to Romanian
via the Anthropic API. Results are cached in-memory to avoid redundant calls.
"""

import logging
import re
from functools import lru_cache

import anthropic

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# In-memory cache: original text -> translated text
_translation_cache: dict[str, str] = {}
_MAX_CACHE = 5000

# Common English words that signal the text is NOT in Romanian
_EN_INDICATORS = re.compile(
    r'\b(with|without|for|and|the|made|from|of|in|our|this|that|'
    r'your|can|has|have|its|soft|set|bag|cup|mug|pen|key|ring|'
    r'classic|bestseller|durable|premium|design|available|includes|'
    r'features|suitable|perfect|ideal|men|women|unisex|children|'
    r'lightweight|waterproof|stainless|steel|cotton|polyester|nylon|'
    r'bottle|jacket|shirt|polo|cap|hat|backpack|umbrella|'
    r'ball|foam|squeeze|anti-stress|holder|opener|case|cover|'
    r'glass|wooden|leather|rubber|foldable|reusable|printed|'
    r'custom|colour|color|size|weight|capacity|piece|item)\b',
    re.IGNORECASE,
)

# Romanian indicators — if present, text is already Romanian
_RO_INDICATORS = re.compile(
    r'[ăîșțâ]|'
    r'\b(din|pentru|sau|care|este|sunt|poate|foarte|bumbac|plastic|'
    r'metal|oțel|inoxidabil|capacitate|culoare|material|personalizare|'
    r'dimensiune|greutate|cantitate|bucăți|produs|include)\b',
    re.IGNORECASE,
)


def _is_english(text: str) -> bool:
    """Heuristic to detect if text is likely English (not Romanian)."""
    if not text or len(text) < 10:
        return False

    ro_matches = len(_RO_INDICATORS.findall(text))
    en_matches = len(_EN_INDICATORS.findall(text))

    # If has Romanian diacritics or Romanian words, it's Romanian
    if ro_matches >= 2:
        return False

    # If has several English words, it's English
    if en_matches >= 2:
        return True

    return False


async def translate_to_romanian(name: str, description: str) -> tuple[str, str]:
    """Translate product name and description to Romanian if they're in English.

    Returns (translated_name, translated_description).
    If already Romanian or translation fails, returns originals.
    """
    name_needs = _is_english(name)
    desc_needs = _is_english(description)

    if not name_needs and not desc_needs:
        return name, description

    # Check cache
    cache_key = f"{name}|||{description}"
    if cache_key in _translation_cache:
        cached = _translation_cache[cache_key]
        parts = cached.split("|||", 1)
        return parts[0], parts[1] if len(parts) > 1 else description

    if not settings.anthropic_api_key:
        return name, description

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        parts_to_translate = []
        if name_needs:
            parts_to_translate.append(f"NUME: {name}")
        if desc_needs:
            parts_to_translate.append(f"DESCRIERE: {description}")

        prompt = (
            "Traduce următorul text despre un produs promoțional din engleză în română. "
            "Traduce COMPLET în română, inclusiv numele produsului. "
            "Păstrează DOAR codul/modelul (ex: 'ST2000', 'Classic-T', 'MO2197') netradus. "
            "Exemplu: 'Classic-T Unisex T-shirt' → 'Classic-T Tricou unisex'. "
            "Răspunde DOAR cu traducerea, "
            "în formatul NUME: ... și/sau DESCRIERE: ... exact ca mai jos.\n\n"
            + "\n".join(parts_to_translate)
        )

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        result_text = response.content[0].text.strip()

        translated_name = name
        translated_desc = description

        # Parse response
        for line in result_text.split("\n"):
            line = line.strip()
            if line.upper().startswith("NUME:"):
                translated_name = line[5:].strip()
            elif line.upper().startswith("DESCRIERE:"):
                translated_desc = line[10:].strip()

        # Cache the result
        if len(_translation_cache) < _MAX_CACHE:
            _translation_cache[cache_key] = f"{translated_name}|||{translated_desc}"

        logger.info(
            "Translated product: '%s' -> '%s'",
            name[:50],
            translated_name[:50],
        )
        return translated_name, translated_desc

    except Exception as e:
        logger.warning("Translation failed: %s", e)
        return name, description
