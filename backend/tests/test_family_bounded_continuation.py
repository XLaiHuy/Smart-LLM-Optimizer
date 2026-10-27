import json
from types import SimpleNamespace

import pytest

from app.routing.ml.family_campaign import continuation_approval, deferred_call


def setup(tmp_path):
    approval = dict(
        job_id="job",
        source_sha256="frozen",
        start_completed=440,
        stop_after_completed=450,
        maximum_new_calls=30,
        api_calls_at_approval=1323,
        retain_unresolved_reserve=True,
        retry_unresolved=False,
        allowed_unknown_call_ids=["old"],
    )
    (tmp_path / "bounded-continuation-approval.json").write_text(json.dumps(approval))
    return approval, SimpleNamespace(id="job", api_calls=1323, completed=440)


def test_only_explicit_old_unknown_is_allowed(tmp_path):
    _, job = setup(tmp_path)
    assert continuation_approval(tmp_path, job, "frozen", {"old"})
    with pytest.raises(ValueError):
        continuation_approval(tmp_path, job, "frozen", {"old", "new-timeout"})


@pytest.mark.parametrize("defect", ["calls", "source", "job", "retry", "release", "limit"])
def test_exception_does_not_expand_scope_or_retry_unknown(tmp_path, defect):
    approval, job = setup(tmp_path)
    source = "frozen"
    if defect == "calls":
        job.api_calls = 1354
    elif defect == "source":
        source = "changed"
    elif defect == "job":
        job.id = "other"
    elif defect == "retry":
        approval["retry_unresolved"] = True
    elif defect == "release":
        approval["retain_unresolved_reserve"] = False
    else:
        approval["stop_after_completed"] = 451
    (tmp_path / "bounded-continuation-approval.json").write_text(json.dumps(approval))
    with pytest.raises(ValueError):
        continuation_approval(tmp_path, job, source, {"old"})


def test_unresolved_pair_is_deferred_without_touching_marker(tmp_path, monkeypatch):
    monkeypatch.setattr("app.routing.ml.family_campaign.cache_key", lambda m, c, messages: c)
    manifest = SimpleNamespace(configurations=[SimpleNamespace(config_id="a")])
    marker = tmp_path / "a.dispatch.json"
    marker.write_text(json.dumps({"call_id": "old"}))
    original = marker.read_bytes()
    assert deferred_call(tmp_path, manifest, (), {"old"})
    assert not deferred_call(tmp_path, manifest, (), {"different"})
    assert marker.read_bytes() == original
