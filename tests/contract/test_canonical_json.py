"""Tests for RFC 8785 Canonical JSON Serialization and SHA-256 Hashing."""

from datetime import datetime
from contracts.canonical import to_canonical_json, compute_canonical_hash


def test_canonical_json_key_sorting():
    """Verify that dictionary keys are sorted lexicographically at all levels."""
    d1 = {"z": 100, "b": 2, "a": {"y": True, "x": False}}
    d2 = {"a": {"x": False, "y": True}, "z": 100, "b": 2}

    json1 = to_canonical_json(d1)
    json2 = to_canonical_json(d2)

    assert json1 == json2
    assert json1 == '{"a":{"x":false,"y":true},"b":2,"z":100}'


def test_canonical_hash_invariance():
    """Verify that different dictionary ordering produces identical SHA-256 digest."""
    payload1 = {"tenant_id": "cust-01", "issue_id": "INC-2041", "active": True}
    payload2 = {"issue_id": "INC-2041", "active": True, "tenant_id": "cust-01"}

    hash1 = compute_canonical_hash(payload1)
    hash2 = compute_canonical_hash(payload2)

    assert hash1 == hash2
    assert len(hash1) == 64
    assert hash1.islower()


def test_canonical_datetime_normalization():
    """Verify that datetime objects serialize into deterministic ISO format."""
    dt = datetime(2026, 11, 23, 10, 30, 0)
    data = {"timestamp": dt, "count": 5}
    expected_json = '{"count":5,"timestamp":"2026-11-23T10:30:00"}'

    assert to_canonical_json(data) == expected_json

