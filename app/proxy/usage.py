"""Usage statistics recording."""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


async def record_usage(
    model: str,
    provider: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    client_key_id: int | None = None,
) -> None:
    """Record token usage (best-effort, does not raise)."""
    try:
        from app.storage.db import get_db
        from app.storage.repositories import HealthEventRepository
        db = await get_db()
        # Use a simple SQL insert
        await db.execute(
            """INSERT INTO usage_log (timestamp, model, provider, prompt_tokens, completion_tokens, total_tokens, client_key_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                time.time(),
                model,
                provider,
                prompt_tokens,
                completion_tokens,
                prompt_tokens + completion_tokens,
                client_key_id,
            ),
        )
        await db.commit()
    except Exception:
        logger.debug("record_usage failed (table may not exist yet)", exc_info=True)
