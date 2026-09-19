from importlib.metadata import version
from time import perf_counter

from gametagger.decisions.jev import JevDecisionEngine
from gametagger.decisions.policy import DecisionPolicy
from gametagger.domain import AnalysisResult, AnalysisRun, EvidenceItem
from gametagger.evidence import prepare_evidence
from gametagger.identity import IdentityManifest, project_upload_manifest, validate_identity
from gametagger.observers.base import Observer
from gametagger.observers.boundary import ObservationBoundary


class AnalysisPipeline:
    def __init__(self, observer: Observer, engine: JevDecisionEngine):
        self.observer = observer
        self.engine = engine
        self.boundary = ObservationBoundary(engine.taxonomy)

    def analyze(
        self,
        *,
        game_id: str,
        evidence: list[EvidenceItem],
        game_title: str | None = None,
        blind_media: bool = False,
        offline: bool = False,
        identity: IdentityManifest | None = None,
        project_id: str | None = None,
    ) -> AnalysisResult:
        start = perf_counter()
        if not evidence or len({e.id for e in evidence}) != len(evidence):
            raise ValueError("Supply nonempty evidence with unique IDs")
        prepared = []
        observations = []
        for item in evidence:
            prepared.append(prepare_evidence(item))
        if project_id is not None:
            if identity is not None:
                raise ValueError("Choose a reviewed manifest or an explicit project upload")
            identity = project_upload_manifest([e for e, _ in prepared], project_id)
        gate = validate_identity(identity, [e for e, _ in prepared])
        eligible = {s.evidence_id for s in gate.sources if s.eligible}
        reviewed = []
        for item, image in prepared:
            reviewed.append(item)
            if item.id not in eligible:
                continue
            # Blind runs strip metadata before observation, not just before classification.
            if blind_media:
                item = item.model_copy(update={"metadata": {}, "source": "blind-media"})
            observed = self.observer.observe(item, image=image)
            self.boundary.validate(observed, item)
            observations.extend(observed)
        prepared = reviewed
        if len({o.id for o in observations}) != len(observations):
            raise ValueError("Observation IDs must be unique across evidence")
        observed_at = perf_counter()
        batch = self.engine.decide(
            game_id=game_id,
            game_title=game_title,
            observations=observations,
            blind_media=blind_media,
            evidence=prepared,
            identity=identity,
            require_identity=True,
        )
        classified_at = perf_counter()
        tags, genre = DecisionPolicy().apply(batch.tags, batch.genre)
        batch.tags, batch.genre = tags, genre
        finished = perf_counter()
        run = AnalysisRun(
            game_id=game_id,
            game_title=None if blind_media else game_title,
            taxonomy_version=self.engine.taxonomy.version,
            observer_model=self.observer.model,
            decision_model=batch.model,
            prompt_version=self.observer.prompt_version,
            decision_prompt_version=self.engine.compiler.prompt_version,
            requested_decision_model=self.engine.gateway.model,
            sdk_versions={
                name: version(name) for name in ["typesafe-sdk", "anthropic", "gametagger"]
            },
            latency_ms=(finished - start) * 1000,
            stage_latency_ms={
                "observe": (observed_at - start) * 1000,
                "decide": (classified_at - observed_at) * 1000,
                "policy": (finished - classified_at) * 1000,
            },
            usage=batch.usage,
            usage_by_stage=batch.usage_by_stage,
            offline=offline,
        )
        return AnalysisResult(
            run=run,
            evidence=prepared,
            observations=observations,
            tags=tags,
            genre=genre,
            execution=batch,
            identity_audit={
                "eligibility": gate.model_dump(mode="json"),
                "manifest": identity.model_dump(mode="json") if identity else None,
            },
        )
