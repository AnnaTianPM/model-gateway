"""Admin API for model and score management."""

from __future__ import annotations

import logging

import yaml
from fastapi import APIRouter, Depends, UploadFile, File
from pydantic import BaseModel

from app.auth.admin import verify_admin

logger = logging.getLogger(__name__)

router = APIRouter()


class ScoreUpdate(BaseModel):
    canonical_model_id: int
    general_score: int = 0
    coding_score: int = 0
    reasoning_score: int = 0
    math_score: int = 0
    writing_score: int = 0
    translation_score: int = 0
    chinese_score: int = 0
    tool_calling_score: int = 0
    vision_score: int = 0
    json_score: int = 0
    source: str = "manual"
    notes: str = ""


@router.get("/models")
async def list_models(_=Depends(verify_admin)):
    """List all canonical models with scores."""
    from app.storage.db import get_db
    from app.storage.repositories import CanonicalModelRepository, ModelScoreRepository

    await get_db()
    models = await CanonicalModelRepository.get_all()
    result = []
    for m in models:
        scores = await ModelScoreRepository.get(m["id"])
        result.append({**m, "scores": scores or {}})
    return result


@router.put("/models/{model_id}/scores")
async def update_scores(model_id: int, data: ScoreUpdate, _=Depends(verify_admin)):
    """Update static scores for a model."""
    from app.storage.db import get_db
    from app.storage.repositories import ModelScoreRepository

    await get_db()
    await ModelScoreRepository.upsert(**data.model_dump())
    return {"ok": True}


@router.get("/models/scores/export")
async def export_scores(_=Depends(verify_admin)):
    """Export all model scores as YAML."""
    from app.storage.db import get_db
    from app.storage.repositories import CanonicalModelRepository, ModelScoreRepository

    await get_db()
    models = await CanonicalModelRepository.get_all()
    export = {"version": 1, "models": {}}
    for m in models:
        scores = await ModelScoreRepository.get(m["id"])
        if scores:
            export["models"][m["canonical_name"]] = {
                "display_name": m["display_name"],
                "context_length": m["context_length"],
                "scores": {k.replace("_score", ""): v for k, v in scores.items() if k.endswith("_score")},
            }
    return export


@router.post("/models/scores/import")
async def import_scores(file: UploadFile = File(...), _=Depends(verify_admin)):
    """Import model scores from YAML file."""
    content = await file.read()
    data = yaml.safe_load(content)
    if not data or "models" not in data:
        return {"ok": False, "error": "Invalid YAML format"}

    from app.storage.db import get_db
    from app.storage.repositories import CanonicalModelRepository, ModelScoreRepository

    await get_db()
    count = 0
    for model_name, model_data in data["models"].items():
        existing = await CanonicalModelRepository.get_by_name(model_name)
        if not existing:
            caps = model_data.get("capabilities", {})
            existing = await CanonicalModelRepository.add(
                canonical_name=model_name,
                display_name=model_data.get("display_name", model_name),
                context_length=model_data.get("context_length", 32768),
                supports_stream=caps.get("stream", True),
                supports_tools=caps.get("tools", False),
                supports_json=caps.get("json", False),
                supports_vision=caps.get("vision", False),
                supports_reasoning=caps.get("reasoning", False),
            )
        scores = model_data.get("scores", {})
        await ModelScoreRepository.upsert(
            canonical_model_id=existing["id"],
            general_score=scores.get("general", 0),
            coding_score=scores.get("coding", 0),
            reasoning_score=scores.get("reasoning", 0),
            math_score=scores.get("math", 0),
            writing_score=scores.get("writing", 0),
            translation_score=scores.get("translation", 0),
            chinese_score=scores.get("chinese", 0),
            tool_calling_score=scores.get("tool_calling", 0),
            vision_score=scores.get("vision", 0),
            json_score=scores.get("json", 0),
            source="import",
        )
        count += 1
    return {"ok": True, "imported": count}
