import re


def slugify(name: str) -> str:
    """Lowercase, dash-separated, at most 64 chars. Raises ValueError if nothing usable remains."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower())[:64].strip("-")
    if not slug:
        raise ValueError(f"name '{name}' must contain at least one letter or digit")
    return slug
