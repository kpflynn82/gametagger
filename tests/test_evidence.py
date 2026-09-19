from pathlib import Path

import pytest
from PIL import Image

from gametagger.domain import EvidenceType
from gametagger.evidence import MAX_IMAGE_BYTES, prepare_evidence


@pytest.mark.parametrize("kind", ["remote", "corrupt", "oversized", "animated", "clip"])
def test_unsupported_evidence_is_rejected_before_provider(evidence, kind):
    path = Path(evidence.uri)
    if kind == "remote":
        evidence.uri = "https://example.com/frame.png"
    elif kind == "corrupt":
        path.write_bytes(b"not an image")
    elif kind == "oversized":
        path.write_bytes(b"x" * (MAX_IMAGE_BYTES + 1))
    elif kind == "animated":
        image = Image.new("RGB", (4, 4), "red")
        image.save(
            path, format="GIF", save_all=True, append_images=[Image.new("RGB", (4, 4), "blue")]
        )
    elif kind == "clip":
        evidence.type = EvidenceType.GAMEPLAY_CLIP
    with pytest.raises((ValueError, OSError)):
        prepare_evidence(evidence)
