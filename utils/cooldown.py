from datetime import datetime, timezone, timedelta
from config import COOLDOWN_DAYS


def get_remaining(last_published_at) -> timedelta | None:
    """מחזיר timedelta של הזמן שנותר, או None אם מותר לפרסם."""
    if last_published_at is None:
        return None
    now = datetime.now(timezone.utc)
    # וודא שיש timezone
    if last_published_at.tzinfo is None:
        last_published_at = last_published_at.replace(tzinfo=timezone.utc)
    next_allowed = last_published_at + timedelta(days=COOLDOWN_DAYS)
    remaining = next_allowed - now
    if remaining.total_seconds() <= 0:
        return None
    return remaining


def format_remaining(remaining: timedelta) -> str:
    total_seconds = int(remaining.total_seconds())
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    parts = []
    if days:
        parts.append(f"{days} ימים")
    if hours:
        parts.append(f"{hours} שעות")
    if minutes and not days:
        parts.append(f"{minutes} דקות")
    return " ו־".join(parts) if parts else "פחות מדקה"
