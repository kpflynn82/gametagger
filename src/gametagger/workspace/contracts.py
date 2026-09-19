from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCreate(Contract):
    title: str = Field(min_length=1, max_length=160)
    release: str = Field(default="Unspecified release", max_length=160)
    platform: Literal["pc", "console", "mobile", "multiplatform"] = "pc"
    entry: Literal["publisher_project", "game_reference", "demo"] = "publisher_project"
    association_confirmed: bool = False
    description: str = Field(default="", max_length=20000)
    source_label: str = Field(default="User-supplied description", max_length=200)
    reference_url: str = Field(default="", max_length=1000)


class AssetView(Contract):
    id: str
    name: str
    kind: str
    sha256: str
    bytes: int
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    url: str
    frames: list[dict[str, Any]] = Field(default_factory=list)


class TagView(Contract):
    id: str
    label: str
    category: str
    state: str | None = None
    human_state: str | None = None
    execution: str
    action: str | None = None
    probabilities: dict[str, float] | None = None
    support_status: str = "Evaluated context; specific support not yet verified."
    context_evidence_ids: list[str] = Field(default_factory=list)
    support_links: list[dict[str, Any]] = Field(default_factory=list)


class ProjectView(Contract):
    id: str
    title: str
    release: str
    platform: str
    entry: str
    identity_status: str
    created_at: str
    approved_primary: str | None = None
    approved_primary_label: str | None = None
    review_version: int = 0
    run_count: int = 0
    assets: list[AssetView] = Field(default_factory=list)


class RunCreate(Contract):
    project_id: str
    mode: Literal["offline", "live"] = "offline"
    idempotency_key: str = Field(min_length=8, max_length=100)


class ReviewCreate(Contract):
    kind: Literal["primary", "identity", "attribute"]
    value: str
    property_id: str | None = None
    reason: str = Field(min_length=8, max_length=2000)
    expected_version: int = Field(ge=0)
    # Approval binds the intended release/project; no automatic external-source mapping.


class RunView(Contract):
    id: str
    project_id: str
    title: str
    release: str
    platform: str
    mode: str
    dataset: Literal["workspace", "demo"] = "workspace"
    status: str
    identity_status: str
    created_at: str
    primary_genre: str | None = None
    primary_label: str | None = None
    primary_status: str
    blocker: str | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[TagView] = Field(default_factory=list)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    assets: list[AssetView] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    distributions: dict[str, Any] = Field(default_factory=dict)
    reviews: list[dict[str, Any]] = Field(default_factory=list)


class CatalogPage(Contract):
    items: list[ProjectView]
    total: int
    page: int
    page_size: int


class Capabilities(Contract):
    environment: str = "Private local workspace"
    user: str
    role: str
    live_enabled: bool = False
    live_reason: str = "No numeric API budget authorized. Live analysis is disabled."
    images: bool = True
    video: bool
    video_status: str = "Experimental preprocessing; temporal recognition not validated"
    max_images: int = 8
    max_image_bytes: int = 5242880
    max_video_bytes: int = 41943040
    max_video_seconds: int = 60
    taxonomy_version: str = "4.1"
    runtime: str = "Local API responding; coding-agent runtime unknown"
    providers: dict[str, bool]
