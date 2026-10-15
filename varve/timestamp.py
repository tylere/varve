from datetime import datetime, timezone


def ts_slug(iso: str) -> str:
    """Filename- and URL-safe UTC timestamp that reads like ISO 8601 and sorts as text,
    e.g. "2026-10-06T22:07:53Z" → "2026-10-06T22-07-53Z"."""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H-%M-%SZ")
