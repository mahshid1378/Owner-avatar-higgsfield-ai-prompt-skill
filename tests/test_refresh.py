"""Spec-drift tripwire (refresh_specs.py, Wave C Tier 1) — pure-function tests.

The diff's whole value is its severity classification: a NEW live capability the
snapshot lacks is DRIFT (the Seedance-4K staleness case); the CLI reporting LESS
than the snapshot (enum:null, missing params/models) is NOTICE, not drift —
because the two sources diverge in detail and a removal-shaped signal is usually
the CLI under-reporting, not a real withdrawal.
"""
import refresh_specs as r


# ── Normalization: both sources collapse to one comparable shape ─────────────

def test_snapshot_view_normalizes_options_and_aspect():
    item = {"id": "seedance_2_0", "output_type": "video",
            "aspect_ratios": ["16:9", "21:9"],
            "parameters": [{"name": "resolution", "type": "string",
                            "default": "720p", "options": ["720p", "1080p", "4k"]}]}
    v = r.snapshot_view(item)
    assert v["id"] == "seedance_2_0"
    assert v["aspect_ratios"] == ["16:9", "21:9"]
    assert v["params"]["resolution"]["options"] == ["1080p", "4k", "720p"]  # sorted
    assert v["params"]["resolution"]["default"] == "720p"


def test_cli_view_maps_enum_and_aspect_param():
    get = {"job_set_type": "seedance_2_0", "type": "video",
           "params": [{"name": "aspect_ratio", "enum": ["16:9", "21:9"]},
                      {"name": "resolution", "default": "720p",
                       "enum": ["720p", "1080p", "4k"]}]}
    v = r.cli_view(get)
    assert v["id"] == "seedance_2_0"
    assert v["aspect_ratios"] == ["16:9", "21:9"]          # from aspect_ratio param
    assert v["params"]["resolution"]["options"] == ["1080p", "4k", "720p"]


def _view(aspect, params):
    return {"id": "m", "output_type": "video", "aspect_ratios": sorted(aspect),
            "params": params}


# ── DRIFT: a new live capability the snapshot lacks ──────────────────────────

def test_new_enum_option_is_drift():
    old = _view(["16:9"], {"resolution": {"options": ["720p", "1080p"], "default": "720p"}})
    new = _view(["16:9"], {"resolution": {"options": ["720p", "1080p", "4k"], "default": "720p"}})
    d = r.diff_model(old, new)
    assert d["drift"] == [{"kind": "options_added", "param": "resolution", "added": ["4k"]}]
    assert d["notice"] == []


def test_new_aspect_ratio_is_drift():
    old = _view(["16:9"], {})
    new = _view(["16:9", "21:9"], {})
    d = r.diff_model(old, new)
    assert d["drift"] == [{"kind": "aspect_ratios", "added": ["21:9"]}]


def test_default_change_is_drift():
    old = _view([], {"resolution": {"options": ["1k", "2k"], "default": "1k"}})
    new = _view([], {"resolution": {"options": ["1k", "2k"], "default": "2k"}})
    d = r.diff_model(old, new)
    assert d["drift"] == [{"kind": "default", "param": "resolution", "from": "1k", "to": "2k"}]


# ── NOTICE: CLI under-reporting must NOT flip the drift state ─────────────────

def test_option_removed_is_notice_not_drift():
    # snapshot enumerates more than the CLI (e.g. clipify fonts: CLI enum=null)
    old = _view([], {"font": {"options": ["inter", "bangers"], "default": None}})
    new = _view([], {"font": {"options": [], "default": None}})  # CLI enum:null → []
    d = r.diff_model(old, new)
    assert d["drift"] == []
    assert d["notice"] == [{"kind": "options_undetailed", "param": "font"}]


def test_both_enumerate_but_cli_dropped_one_is_notice():
    old = _view([], {"mode": {"options": ["std", "fast", "turbo"], "default": "std"}})
    new = _view([], {"mode": {"options": ["std", "fast"], "default": "std"}})
    d = r.diff_model(old, new)
    assert d["drift"] == []
    assert d["notice"] == [{"kind": "options_removed", "param": "mode", "removed": ["turbo"]}]


def test_param_missing_from_cli_is_notice():
    old = _view([], {"resolution": {"options": ["720p"], "default": "720p"}})
    new = _view([], {})
    d = r.diff_model(old, new)
    assert d["drift"] == []
    assert d["notice"] == [{"kind": "param_missing", "param": "resolution"}]


def test_aspect_removed_is_notice():
    old = _view(["16:9", "21:9"], {})
    new = _view(["16:9"], {})
    d = r.diff_model(old, new)
    assert d["drift"] == []
    assert d["notice"] == [{"kind": "aspect_ratios_gone", "removed": ["21:9"]}]


def test_identical_views_are_clean():
    v = _view(["16:9"], {"resolution": {"options": ["720p", "4k"], "default": "720p"}})
    assert r.diff_model(v, dict(v)) == {"drift": [], "notice": []}


# ── Catalog level: membership is notice, added capability is drift ───────────

def test_catalog_membership_is_notice_not_drift():
    old = {"a": _view([], {}), "b": _view([], {})}      # snapshot tracks a, b
    new = {"a": _view([], {}), "c": _view([], {})}      # CLI has a, c
    diff = r.diff_catalog(old, new)
    assert diff["models_removed"] == ["b"]   # snapshot-only → notice
    assert diff["models_added"] == ["c"]     # CLI-only (new/utility) → notice
    assert r.has_drift(diff) is False        # membership alone is NOT drift


def test_catalog_surfaces_shared_model_drift():
    old = {"a": _view(["16:9"], {})}
    new = {"a": _view(["16:9", "21:9"], {}), "util": _view([], {})}
    diff = r.diff_catalog(old, new)
    assert r.has_drift(diff) is True
    assert diff["models_changed"]["a"]["drift"][0]["kind"] == "aspect_ratios"


# ── v2 self-diff: any_change counts EVERY difference (both sides are the CLI) ──

def test_any_change_false_when_identical():
    v = {"a": _view(["16:9"], {"r": {"options": ["720p"], "default": "720p"}})}
    assert r.any_change(r.diff_catalog(v, {k: dict(x) for k, x in v.items()})) is False


def test_any_change_true_on_new_model():
    old = {"a": _view([], {})}
    new = {"a": _view([], {}), "b": _view([], {})}
    assert r.any_change(r.diff_catalog(old, new)) is True


def test_any_change_true_on_removed_model():
    old = {"a": _view([], {}), "b": _view([], {})}
    new = {"a": _view([], {})}
    assert r.any_change(r.diff_catalog(old, new)) is True


def test_any_change_true_on_a_notice_that_has_drift_false():
    # an option REMOVED is a notice (has_drift False) but a real CLI change
    # (any_change True) — this is the whole point of the self-diff vs snapshot-diff
    old = {"a": _view([], {"mode": {"options": ["std", "fast", "turbo"], "default": "std"}})}
    new = {"a": _view([], {"mode": {"options": ["std", "fast"], "default": "std"}})}
    diff = r.diff_catalog(old, new)
    assert r.has_drift(diff) is False   # snapshot-diff would stay quiet
    assert r.any_change(diff) is True   # self-diff catches it
