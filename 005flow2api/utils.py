"""Utility functions for batch image generation tool."""
import json
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Character:
    """Character data parsed from JSON input."""
    name: str
    aliases: str = ""
    description: str = ""
    index: int = 0

    @property
    def display_aliases(self) -> str:
        return self.aliases if self.aliases else self.name

    @property
    def short_prompt(self) -> str:
        return self.description[:40] + "..." if len(self.description) > 40 else self.description


def parse_prompts(text: str) -> list[str]:
    """Split multi-line text into individual prompts, filtering empty lines."""
    lines = text.strip().splitlines()
    return [line.strip() for line in lines if line.strip()]


def _strip_markdown_code_block(text: str) -> str:
    """Remove markdown code fences (```json / ```) from text."""
    text = text.strip()
    if text.startswith("```"):
        text = text[3:]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    return text


def parse_characters_json(text: str) -> list[Character]:
    """Parse JSON array into Character list. Handles markdown code blocks."""
    text = _strip_markdown_code_block(text)
    if not text:
        return []
    if text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                chars = []
                for i, item in enumerate(data):
                    if isinstance(item, dict) and "name" in item:
                        chars.append(Character(
                            name=item.get("name", ""),
                            aliases=item.get("aliases", ""),
                            description=item.get("description", ""),
                            index=i,
                        ))
                if chars:
                    return chars
        except json.JSONDecodeError:
            pass
    return []


def sanitize_filename(text: str, max_len: int = 50) -> str:
    """Remove characters invalid in filenames and truncate."""
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_len]


def extract_image_url_from_content(content: str) -> Optional[str]:
    """Extract image URL from SSE delta content like `![Generated Image](url)`."""
    # Standard markdown image with direct URL
    match = re.search(r"!\[.*?\]\((https?://\S+)\)", content)
    if match:
        return match.group(1)
    # data:image/url;base64,<actual_url> — the URL is treated as the "base64 data"
    # and may be followed by expiration notes etc. before the closing paren
    match = re.search(r"!\[.*?\]\((data:image/url;base64,)([^\s)]+)", content)
    if match:
        return match.group(1) + match.group(2)
    # data:image/<type>;base64,<actual_base64_data>
    match = re.search(r"!\[.*?\]\((data:image/\S+;base64,\S+)\)", content)
    if match:
        return match.group(1)
    return None


ASPECT_RATIO_MAP = {
    "横屏 (16:9)": "landscape",
    "竖屏 (9:16)": "portrait",
    "方形 (1:1)": "square",
    "4:3": "four-three",
    "3:4": "three-four",
}

RESOLUTION_MAP = {
    "1K": "1k",
    "2K": "2k",
    "4K": "4k",
}

# Map aspect_ratio values to OpenAI-compatible size strings
ASPECT_RATIO_SIZE_MAP = {
    "square": "1024x1024",
    "landscape": "1792x1024",
    "portrait": "1024x1792",
    "four-three": "1440x1080",
    "three-four": "1080x1440",
}


_KNOWN_RESOLUTIONS = {"1k", "2k", "4k", "1080p"}

def build_full_model_name(base_model: str, aspect_ratio: str, resolution: str, remote: bool = False) -> str:
    """Build full model name with aspect ratio and resolution suffixes.

    Local: `gemini-3.1-flash-image` + `square` + `2k` → `gemini-3.1-flash-image-square-2k`
    Remote: returns the base model name unchanged (New API etc. use bare names).
    """
    if remote:
        return base_model
    model = f"{base_model}-{aspect_ratio}"
    base_lower = base_model.lower()
    already_has_res = any(base_lower.endswith(f"-{r}") for r in _KNOWN_RESOLUTIONS)
    if resolution and resolution != "1k" and not already_has_res:
        model = f"{model}-{resolution}"
    return model
