from fastapi import FastAPI

from gametagger.config import get_settings
from gametagger.taxonomy import load_taxonomy

app = FastAPI(title="GameTagger v2", version="0.1.0")


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "decision_engine": settings.decision_engine,
        "jev_shadow_mode": settings.jev_shadow_mode,
        "typesafe_configured": bool(settings.typesafe_api_key),
    }


@app.get("/taxonomy")
def taxonomy() -> dict:
    spec = load_taxonomy()
    return {
        "version": spec.version,
        "pilot_tag_count": len(spec.tags),
        "primary_genre_count": len(spec.primary_genres),
        "tags": [
            {
                "id": tag.id,
                "label": tag.label,
                "category": tag.category,
                "evidence_class": tag.evidence_class,
            }
            for tag in spec.tags
        ],
    }
