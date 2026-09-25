import pytest
from PIL import Image

from gametagger.domain import EvidenceItem, EvidenceType
from gametagger.taxonomy import load_taxonomy


@pytest.fixture(autouse=True)
def _no_ambient_claude_settings(monkeypatch):
    """Offline tests never pick up a real Claude key or model from the developer's environment."""
    monkeypatch.delenv("GAMETAGGER_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OBSERVER_MODEL", raising=False)


@pytest.fixture
def taxonomy():
    return load_taxonomy()


@pytest.fixture
def evidence(tmp_path):
    path = tmp_path / "frame.png"
    Image.new("RGB", (32, 32), "gray").save(path)
    return EvidenceItem(
        id="frame-1", type=EvidenceType.GAMEPLAY_IMAGE, source="test-upload", uri=str(path)
    )
