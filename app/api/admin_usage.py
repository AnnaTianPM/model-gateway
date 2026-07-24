"""Admin API for usage statistics."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends

from app.auth.admin import verify_admin

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/usage")
async def get_usage(days: int = 1, _=Depends(verify_admin)):
    """Get usage statistics."""
    from app.storage.db import get_db

    db = await get_db()
    cutoff = time.time() - days * 86400

    try:
        cursor = await db.execute(
            """SELECT timestamp, model, provider, prompt_tokens, completion_tokens, total_tokens, client_key_id
               FROM usage_log WHERE timestamp >= ?
               ORDER BY timestamp DESC LIMIT 10000""",
            (cutoff,),
        )
        rows = await cursor.fetchall()
    except Exception:
        return {"days": days, "total": {"pt": 0, "ct": 0, "tt": 0, "requests": 0}, "by_day": [], "by_model": []}

    total = {"pt": 0, "ct": 0, "tt": 0, "requests": 0}
    by_day = {}
    by_model = {}

    for row in rows:
        ts, model, provider, pt, ct, tt, _ = row
        pt = pt or 0
        ct = ct or 0
        tt = tt or (pt + ct)
        day = time.strftime("%Y-%m-%d", time.localtime(ts))

        total["pt"] += pt
        total["ct"] += ct
        total["tt"] += tt
        total["requests"] += 1

        d = by_day.setdefault(day, {"pt": 0, "ct": 0, "tt": 0, "requests": 0})
        d["pt"] += pt
        d["ct"] += ct
        d["tt"] += tt
        d["requests"] += 1

        mk = f"{provider} · {model}"
        mm = by_model.setdefault(mk, {"pt": 0, "ct": 0, "tt": 0, "requests": 0, "provider": provider, "model": model})
        mm["pt"] += pt
        mm["ct"] += ct
        mm["tt"] += tt
        mm["requests"] += 1

    by_day_list = [{"date": d, **v} for d, v in sorted(by_day.items())]
    by_model_list = [
        {"provider": v["provider"], "model": v["model"], "pt": v["pt"], "ct": v["ct"], "tt": v["tt"], "requests": v["requests"]}
        for _, v in sorted(by_model.items(), key=lambda x: -x[1]["tt"])
    ]

    return {"days": days, "total": total, "by_day": by_day_list, "by_model": by_model_list}
