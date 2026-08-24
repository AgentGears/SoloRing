"""M10A-4c controls — type-exact runtime value closure (review residual)."""
import pytest

from soloring.spatial.package3 import (
    Package3Invalid,
    _json_domain_equal as eq,
    _validate_json_domain,
    check_runtime_closure,
    parse_profile_v2,
)


def test_int_vs_float_mismatch():
    assert not eq(1, 1.0)
    assert not eq(1.0, 1)


def test_bool_vs_int_mismatch():
    assert not eq(True, 1)
    assert not eq(1, True)
    assert eq(True, True)


def test_nested_list_mismatch():
    assert not eq([1], [1.0])
    assert eq([1], [1])


def test_nested_dict_mismatch():
    assert not eq({"x": 1}, {"x": 1.0})
    assert eq({"x": 1}, {"x": 1})


def test_string_exact_pass():
    assert eq("unipc", "unipc")
    assert not eq("unipc", "euler")


def _profile_with_expected(expected):
    return parse_profile_v2({
        "schema_version": 2, "profile_id": "p", "profile_version": 1,
        "workflow_id": "wf", "workflow_version": 1,
        "model": {"id": "m", "version": "1"},
        "channels": {}, "rules": [], "parameter_overrides": {},
        "spatial": {
            "spatial_document_schema": 1, "max_control_streams": 3,
            "roles": {"spatial.world_depth": {"kind": "derived", "capacity": 1},
                      "spatial.entity_depth": {"kind": "derived", "capacity": 2}},
            "runtime_requirements": {
                "policy": {"kind": "template_policy", "name": "scheduler",
                           "proof": {"mode": "template_node_field",
                                     "value": "160/scheduler",
                                     "expected": expected}}},
            "advisory_omissions": []}})


def _closure(expected, template_value):
    prof = _profile_with_expected(expected)
    template = {"160": {"class_type": "WanVideoSampler",
                        "inputs": {"scheduler": template_value}}}
    return check_runtime_closure(prof["spatial"], fingerprint=None,
                                 template=template)


def test_closure_int_vs_float_template_fails():
    # captured template float vs integer expected -> mismatch
    assert _closure(1, 1.0) == ["policy"]
    # float expected NEVER reaches closure: rejected at parse
    with pytest.raises(Package3Invalid, match="float"):
        _profile_with_expected(1.0)


def test_closure_scheduler_exact_passes_euler_fails():
    assert _closure("unipc", "unipc") == []
    assert _closure("unipc", "euler") == ["policy"]


def test_non_json_expected_rejected_for_dict_callers():
    for bad in (float("nan"), float("inf"), {"k": float("nan")},
                (1, 2), {1: "x"}, 2 ** 60, {"d": 1.5}):
        with pytest.raises(Package3Invalid):
            _profile_with_expected(bad)


def test_valid_expected_domains_accepted():
    for good in (None, True, "x", 5, [1, "a"], {"k": [1, {"n": None}]}):
        _profile_with_expected(good)
