"""Single-writer, evidence-gated guidance promotion over immutable SQLite artifacts.

Workers may stage candidates, but only ``PromotionCoordinator`` may invoke the
active-guidance CAS.  Before that CAS, it verifies the persisted candidate,
validation, paired-replay audit, and frozen-manifest chain against the currently
active baseline.  This prevents a hand-staged version or stale replay from
becoming active merely because it has a valid guidance artifact.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from . import state as state_module
from .guidance import GuidanceValidationError, validate_guidance_artifact
from .replay import PROMOTION_READY


@dataclass(frozen=True)
class PromotionDecision:
    applied: bool
    action: str
    context_id: str
    objective_bucket: str
    guidance_version: str
    previous_guidance_version: str | None
    expected_revision: int
    resulting_revision: int
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "action": self.action,
            "context_id": self.context_id,
            "objective_bucket": self.objective_bucket,
            "guidance_version": self.guidance_version,
            "previous_guidance_version": self.previous_guidance_version,
            "expected_revision": self.expected_revision,
            "resulting_revision": self.resulting_revision,
            "reason": self.reason,
        }


def _version(context_id: str, bucket: str, guidance_text: str, metadata: Mapping[str, Any]) -> str:
    digest = sha256(
        ("\x1f".join((context_id, bucket, guidance_text, repr(sorted(dict(metadata).items()))))).encode("utf-8")
    ).hexdigest()[:24]
    return f"dspy-rlm-{digest}"


def _object(value: Any) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, Mapping) else None


def _json_object(value: Any) -> dict[str, Any] | None:
    try:
        return _object(json.loads(value)) if isinstance(value, str) else _object(value)
    except (TypeError, ValueError):
        return None


class PromotionCoordinator:
    """The only component permitted to change an active guidance pointer."""

    def __init__(self, plugin_dir: str | Path | None = None, *, state_store: state_module.StateStore | None = None, coordinator_id: str = "coordinator"):
        root = Path(plugin_dir) if plugin_dir is not None else Path(__file__).resolve().parents[1]
        self.state = state_store or state_module.StateStore(root)
        self.store = self.state.store
        self.coordinator_id = f"coordinator:{str(coordinator_id or 'default')}"

    def current(self, context_id: str, objective_bucket: str) -> dict[str, Any] | None:
        return self.store.get_active_guidance(str(context_id), str(objective_bucket))

    def stage(
        self,
        context_id: str,
        objective_bucket: str,
        guidance_text: str,
        *,
        objective_signature: str = "",
        guidance_version: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        """Append an immutable candidate artifact without changing active state."""
        if not context_id or not objective_bucket:
            raise ValueError("context_id and objective_bucket are required")
        text = str(guidance_text or "")
        if not text:
            raise ValueError("guidance_text is required")
        detail = dict(metadata or {})
        serialized = detail.get("guidance_artifact")
        if isinstance(serialized, Mapping):
            try:
                artifact = validate_guidance_artifact(serialized)
            except (GuidanceValidationError, TypeError, ValueError) as error:
                raise ValueError(f"guidance_artifact must be schema-valid: {error}") from error
            if artifact.context_id != str(context_id) or artifact.objective_bucket != str(objective_bucket):
                raise ValueError("guidance_artifact scope does not match the staged scope")
            if artifact.artifact_id != str(guidance_version or artifact.artifact_id):
                raise ValueError("guidance_artifact ID does not match guidance_version")
            # Rendering is fixed application text; accepting arbitrary staged prose
            # alongside a strict artifact would reintroduce an injection seam.
            from .guidance import render_guidance_artifact
            if text != render_guidance_artifact(artifact):
                raise ValueError("guidance_text does not match the schema-valid guidance artifact")
            guidance_version = artifact.artifact_id
        version = str(guidance_version or _version(str(context_id), str(objective_bucket), text, detail))
        self.store.append_guidance_version(version, str(context_id), str(objective_bucket), str(objective_signature), text, detail)
        return version

    def _promotion_evidence(
        self,
        context_id: str,
        objective_bucket: str,
        guidance_version: str,
        active: Mapping[str, Any] | None,
    ) -> tuple[dict[str, Any] | None, str]:
        """Verify the immutable candidate-to-replay evidence chain before CAS.

        All identities are recovered from persisted records rather than caller
        detail.  Missing, malformed, mismatched, or non-ready evidence is a
        fail-closed refusal.  The baseline replay identifier is the active
        guidance version; it must match both baseline fields recorded by replay.
        """
        if not active:
            return None, "missing_active_baseline"
        baseline_version = str(active.get("guidance_version") or "")
        if not baseline_version:
            return None, "missing_active_baseline"

        staged = self.store.get_guidance_version(guidance_version)
        metadata = _object(staged.get("metadata") if staged else None)
        identifiers = _object(metadata.get("persistence") if metadata else None)
        if not staged or not metadata or not identifiers:
            return None, "missing_persisted_candidate_evidence"
        required_ids = ("run_id", "candidate_id", "evaluation_id", "replay_audit_id", "replay_manifest_id")
        if any(not isinstance(identifiers.get(name), str) or not identifiers[name] for name in required_ids):
            return None, "missing_persisted_candidate_evidence"
        candidate_id = identifiers["candidate_id"]
        evaluation_id = identifiers["evaluation_id"]
        audit_id = identifiers["replay_audit_id"]
        manifest_id = identifiers["replay_manifest_id"]
        run_id = identifiers["run_id"]

        # Read linked append-only rows together. Store exposes write-safe APIs,
        # while this coordinator needs an exact, read-only evidence join before
        # requesting its one CAS mutation.
        with self.store._connect() as conn:
            candidate_row = conn.execute(
                "SELECT run_id,guidance_version,candidate_json FROM candidates "
                "WHERE candidate_id=? AND context_id=? AND objective_bucket=?",
                (candidate_id, str(context_id), str(objective_bucket)),
            ).fetchone()
            evaluation_row = conn.execute(
                "SELECT candidate_id,evaluation_json FROM evaluations WHERE evaluation_id=?",
                (evaluation_id,),
            ).fetchone()
            audit_row = conn.execute(
                "SELECT candidate_id,manifest_id,audit_json FROM replay_audits WHERE audit_id=?",
                (audit_id,),
            ).fetchone()
            manifest_row = conn.execute(
                "SELECT context_id,kind,payload_json FROM sample_manifests WHERE manifest_id=?",
                (manifest_id,),
            ).fetchone()

        if not candidate_row or not evaluation_row or not audit_row or not manifest_row:
            return None, "missing_persisted_candidate_evidence"
        candidate = _json_object(candidate_row["candidate_json"])
        evaluation = _json_object(evaluation_row["evaluation_json"])
        audit = _json_object(audit_row["audit_json"])
        manifest = _json_object(manifest_row["payload_json"])
        if not candidate or not evaluation or not audit or not manifest:
            return None, "malformed_persisted_promotion_evidence"

        # Candidate, evaluation, audit, manifest, and staged metadata must form
        # one coherent immutable record set for this exact candidate version.
        if (
            str(candidate_row["run_id"] or "") != run_id
            or str(candidate_row["guidance_version"] or "") != str(guidance_version)
            or str(candidate.get("candidate_id") or "") != candidate_id
            or str(candidate.get("run_id") or "") != run_id
            or str(candidate.get("guidance_version") or "") != str(guidance_version)
            or str(candidate.get("replay_audit_id") or "") != audit_id
            or str(candidate.get("replay_manifest_id") or "") != manifest_id
            or str(evaluation_row["candidate_id"] or "") != candidate_id
            or str(evaluation.get("run_id") or "") != run_id
            or str(evaluation.get("replay_manifest_id") or "") != manifest_id
            or str(audit_row["candidate_id"] or "") != candidate_id
            or str(audit_row["manifest_id"] or "") != manifest_id
            or str(manifest_row["context_id"] or "") != str(context_id)
            or str(manifest_row["kind"] or "") != "paired_replay"
            or str(manifest.get("manifest_id") or "") != manifest_id
        ):
            return None, "promotion_evidence_linkage_mismatch"

        candidate_validation = _object(candidate.get("validation"))
        evaluation_validation = _object(evaluation.get("validation"))
        if not candidate_validation or not evaluation_validation or not bool(candidate_validation.get("passed")) or not bool(evaluation_validation.get("passed")):
            return None, "candidate_validation_not_ready"
        if (
            audit.get("decision") != PROMOTION_READY
            or not bool(audit.get("promotion_ready"))
            or not bool(audit.get("passed"))
            or str(audit.get("manifest_id") or "") != manifest_id
            or str(audit.get("manifest_digest") or "") != str(manifest.get("digest") or "")
            or str(audit.get("baseline_revision") or "") != baseline_version
            or str(audit.get("active_baseline_revision") or "") != baseline_version
        ):
            return None, "replay_not_promotion_ready"

        provenance = _object(audit.get("provenance"))
        if not provenance or str(provenance.get("candidate_guidance_version") or "") != str(guidance_version):
            return None, "promotion_evidence_linkage_mismatch"
        return {
            "candidate_id": candidate_id,
            "run_id": run_id,
            "evaluation_id": evaluation_id,
            "replay_audit_id": audit_id,
            "replay_manifest_id": manifest_id,
            "replayed_baseline_guidance_version": baseline_version,
        }, ""

    def promote(
        self,
        context_id: str,
        objective_bucket: str,
        guidance_version: str,
        *,
        expected_revision: int | None,
        detail: Mapping[str, Any] | None = None,
    ) -> PromotionDecision:
        """Atomically promote only a persisted, replay-ready staged version."""
        active = self.current(context_id, objective_bucket)
        observed = int(active["revision"]) if active else 0
        expected = observed if expected_revision is None else int(expected_revision)
        previous = str(active["guidance_version"]) if active else None
        evidence, refusal = self._promotion_evidence(str(context_id), str(objective_bucket), str(guidance_version), active)
        if evidence is None:
            return PromotionDecision(
                applied=False, action="promote", context_id=str(context_id), objective_bucket=str(objective_bucket),
                guidance_version=str(guidance_version), previous_guidance_version=previous,
                expected_revision=expected, resulting_revision=observed, reason=refusal,
            )
        applied, resulting = self.store.compare_and_swap_active_guidance(
            str(context_id), str(objective_bucket), str(guidance_version),
            expected_revision=expected,
            actor_id=self.coordinator_id,
            detail={"authority": "coordinator", "promotion_evidence": evidence, **dict(detail or {})},
            action="promote",
        )
        return PromotionDecision(
            applied=applied, action="promote", context_id=str(context_id), objective_bucket=str(objective_bucket),
            guidance_version=str(guidance_version), previous_guidance_version=previous,
            expected_revision=expected, resulting_revision=int(resulting),
            reason="promoted" if applied else "active_revision_conflict",
        )

    def rollback(
        self,
        context_id: str,
        objective_bucket: str,
        guidance_version: str,
        *,
        expected_revision: int | None,
        detail: Mapping[str, Any] | None = None,
    ) -> PromotionDecision:
        """CAS rollback to an existing immutable version, retaining all history."""
        active = self.current(context_id, objective_bucket)
        observed = int(active["revision"]) if active else 0
        expected = observed if expected_revision is None else int(expected_revision)
        previous = str(active["guidance_version"]) if active else None
        applied, resulting = self.store.rollback_active_guidance(
            str(context_id), str(objective_bucket), str(guidance_version),
            expected_revision=expected,
            actor_id=self.coordinator_id,
            detail={"authority": "coordinator", **dict(detail or {})},
        )
        return PromotionDecision(
            applied=applied, action="rollback", context_id=str(context_id), objective_bucket=str(objective_bucket),
            guidance_version=str(guidance_version), previous_guidance_version=previous,
            expected_revision=expected, resulting_revision=int(resulting),
            reason="rolled_back" if applied else "active_revision_conflict",
        )


def stage_candidate(plugin_dir: str | Path, **kwargs: Any) -> str:
    return PromotionCoordinator(plugin_dir).stage(**kwargs)


def promote_candidate(plugin_dir: str | Path, **kwargs: Any) -> dict[str, Any]:
    return PromotionCoordinator(plugin_dir).promote(**kwargs).as_dict()


def rollback_candidate(plugin_dir: str | Path, **kwargs: Any) -> dict[str, Any]:
    return PromotionCoordinator(plugin_dir).rollback(**kwargs).as_dict()


# Names matching the scheduler design's compact promotion interface.
def promote(plugin_dir: str | Path, **kwargs: Any) -> dict[str, Any]:
    return promote_candidate(plugin_dir, **kwargs)


def rollback(plugin_dir: str | Path, **kwargs: Any) -> dict[str, Any]:
    return rollback_candidate(plugin_dir, **kwargs)
