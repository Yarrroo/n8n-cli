"""Summarizer: the core AI feature. Tests cover all 6 flags + binary + budget."""

from __future__ import annotations

import base64
import json

from n8n_cli.output.summarize import SummarizeOptions, summarize_items


def _bytes_of(obj: object) -> int:
    return len(json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))


def test_empty_items_returns_zero_count_no_sample() -> None:
    out = summarize_items([])
    assert out["item_count"] == 0
    assert out["sample"] == []
    assert out["truncated"] is False


def test_default_returns_one_sample() -> None:
    items = [{"id": i} for i in range(5)]
    out = summarize_items(items)
    assert out["item_count"] == 5
    assert out["schema"] == {"id": "integer"}
    assert out["sample"] == [{"id": 0}]
    assert out["truncated"] is True


def test_head_overrides_sample() -> None:
    items = [{"id": i} for i in range(10)]
    out = summarize_items(items, SummarizeOptions(sample=1, head=3))
    assert [x["id"] for x in out["sample"]] == [0, 1, 2]
    assert out["truncated"] is True


def test_schema_only_omits_sample_but_keeps_count() -> None:
    items = [{"id": 1}, {"id": 2}]
    out = summarize_items(items, SummarizeOptions(schema_only=True))
    assert out["sample"] == []
    assert out["item_count"] == 2
    assert out["schema"] == {"id": "integer"}
    assert out["truncated"] is True


def test_full_escape_hatch_returns_raw() -> None:
    items = [{"id": 1, "name": "keep"}]
    out = summarize_items(items, SummarizeOptions(full=True))
    assert out == {"full": items}


def test_jsonpath_extract() -> None:
    items = [{"id": 1, "meta": {"tag": "a"}}, {"id": 2, "meta": {"tag": "b"}}]
    out = summarize_items(items, SummarizeOptions(path="$[*].meta.tag"))
    assert out["extracted"] == ["a", "b"]
    assert out["item_count"] == 2


def test_two_mb_payload_summarized_under_one_kb() -> None:
    """Success criterion from task.md: 2MB input → ≤1KB default output."""
    # ~5000 uniform items → comfortably over 2 MB once serialized.
    items = [
        {
            "id": f"u_{i}",
            "name": f"User {i} has an annoyingly long name to inflate payload size X" * 4,
            "email": f"user{i}@example.com",
            "tags": ["a", "b", "c"] * 5,
            "metadata": {"created_at": "2026-04-21T10:00:00Z", "score": i * 1.5},
        }
        for i in range(5000)
    ]
    assert _bytes_of(items) > 2_000_000

    out = summarize_items(items)
    serialized = json.dumps(out, ensure_ascii=False)
    assert len(serialized.encode()) <= 1024, f"summary exceeds 1KB budget: {len(serialized)} bytes"
    assert out["item_count"] == 5000
    assert isinstance(out["schema"], dict)


def test_binary_replaced_with_metadata() -> None:
    big_payload = base64.b64encode(b"\x00" * 100_000).decode()
    items = [
        {
            "json": {"id": 1},
            "binary": {
                "file": {
                    "data": big_payload,
                    "mimeType": "image/png",
                    "fileName": "avatar.png",
                    "fileSize": 100_000,
                }
            },
        }
    ]
    out = summarize_items(items, SummarizeOptions(sample=1))
    sample = out["sample"][0]
    assert "data" not in sample["binary"]["file"]
    assert sample["binary"]["file"]["mime_type"] == "image/png"
    assert sample["binary"]["file"]["file_name"] == "avatar.png"
    assert sample["binary"]["file"]["size_bytes"] == 100_000
    assert sample["binary"]["file"]["_binary"] is True


def test_long_string_truncated_in_sample() -> None:
    items = [{"description": "x" * 5000}]
    out = summarize_items(items, SummarizeOptions(sample=1))
    sample = out["sample"][0]
    assert len(sample["description"]) < 400
    assert sample["description"].endswith("more chars)")


def test_max_bytes_trims_sample_preserves_schema() -> None:
    # Each item ~1KB. With budget 512 we can't fit any sample, but schema must stay.
    items = [{"payload": "x" * 900, "id": i} for i in range(3)]
    out = summarize_items(items, SummarizeOptions(sample=3, max_bytes=512))
    # Schema stays; sample trimmed down.
    assert out["schema"] is not None
    assert _bytes_of(out) <= 512 or out["sample"] == []


def test_heterogeneous_items_get_oneof_schema() -> None:
    items = [{"a": 1}, {"b": 2}, {"c": 3}]
    out = summarize_items(items, SummarizeOptions(sample=1))
    assert "oneOf" in out["schema"]
