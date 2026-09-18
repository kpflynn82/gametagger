import pytest
from PIL import Image

from gametagger.domain import EvidenceItem, EvidenceType
from gametagger.taxonomy import load_taxonomy


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
