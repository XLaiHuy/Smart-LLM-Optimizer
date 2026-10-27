"""Audit only: inspect frozen metadata and family evidence, never fit or call API."""
import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from app.routing.ml.multi import MultiArtifact
from app.routing.task_groups import FAMILIES, TaskGroupPolicy


def main(args):
    raw = args.artifact.read_text(encoding='utf-8')
    artifact = MultiArtifact.model_validate_json(raw)
    semantic_hash = hashlib.sha256(artifact.model_dump_json().encode()).hexdigest()
    engine = SimpleNamespace(hash=semantic_hash, multi=SimpleNamespace(artifact=artifact))
    policy = TaskGroupPolicy(args.bundle, engine)
    profiles = policy.bundle['profiles'] if policy.bundle else {}
    report = {
        'created_at': datetime.now(UTC).isoformat(),
        'scope': 'family-policy-admission-audit', 'provider_calls': 0,
        'ml_artifact_hash': semantic_hash, 'artifact_file_sha256': hashlib.sha256(args.artifact.read_bytes()).hexdigest(),
        'existing_thresholds': {p.config_id: p.threshold for p in artifact.predictors},
        'status': policy.status,
        'families': {family: {
            'decision': 'qualified_profile' if family in profiles else 'retain_current_policy',
            'reason': 'bound_independent_evidence_passed' if family in profiles else 'no_accepted_fresh_family_evidence',
            'minimum_independent_holdout_groups': 100,
            'required': ['frozen_train_calibration_threshold_splits', 'fresh_unseen_family_holdout', 'reviewed_content_grader', 'same_three_serving_profiles', 'serving_e2e_latency', 'zero_critical_regression', 'one_sided_95_regression_upper_at_most_0.03'],
        } for family in FAMILIES},
        'limitations': ['Existing inspected math/MCQ HOLDOUT is not a fresh six-family HOLDOUT.', 'Previously measured 24-turn audit is functional coverage, not 100 independent memory conversations.', 'No new thresholds, artifacts, live approval or funds were modified.'],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': policy.status, 'families_enabled': len(profiles), 'families_retaining_policy': len(FAMILIES)-len(profiles), 'output': str(args.output)}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, default=Path('config/router_attention_operator_accepted.json'))
    parser.add_argument('--bundle', type=Path, default=Path('config/task_routing_profiles.json'))
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args())
