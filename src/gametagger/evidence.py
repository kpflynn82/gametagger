import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image

from gametagger.domain import EvidenceItem, EvidenceType

MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp", "GIF": "image/gif"}


def prepare_evidence(item: EvidenceItem) -> tuple[EvidenceItem, bytes | None]:
    """Load a local image once, verify format, and bind provenance to those exact bytes."""
    item = item.model_copy(deep=True)
    if item.type != EvidenceType.GAMEPLAY_IMAGE:
        raise ValueError("Milestone 1 supports gameplay_image evidence with optional text metadata")
    if not item.uri or "://" in item.uri:
        raise ValueError("Image evidence requires a local filesystem path")
    path = Path(item.uri).resolve()
    with path.open("rb") as stream:
        data = stream.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Image exceeds the 5 MiB input limit")
    with Image.open(BytesIO(data)) as image:
        media_type = IMAGE_TYPES.get(image.format)
        if media_type is None or max(image.size) > 8000 or image.n_frames != 1:
            raise ValueError(
                "Use a single PNG, JPEG, WEBP, or GIF image up to 8000 pixels per side"
            )
        image.verify()
    digest = hashlib.sha256(data).hexdigest()
    if item.sha256 is not None and item.sha256 != digest:
        raise ValueError("Evidence hash does not match image bytes")
    item.sha256 = digest
    item.uri = str(path)
    item.media_type = media_type
    return item, data
