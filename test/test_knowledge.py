import json

import pytest

import knowledge_index as kb
from evaluate import FixtureEmbeddings, run_cases


@pytest.fixture
def index(tmp_path, monkeypatch):
    path = tmp_path / "bundle.json"
    monkeypatch.setenv("SHOP_KB_INDEX", str(path))
    monkeypatch.setenv("SHOP_KB_MIN_SCORE", "0.65")
    return path


def test_index_repeatable_and_hit_is_from_actual_chunk(index):
    model = FixtureEmbeddings()
    data = kb.build_index(index, model)
    before = index.read_bytes()
    kb.build_index(index, model)
    assert index.read_bytes() == before
    assert data["documents"] >= 20
    assert len(data["chunks"]) > data["documents"]
    matches = kb.retrieve("主动降噪和被动隔音有什么区别", model)
    assert matches["sources"][0]["id"] == "KB-001"
    expected = next(row for row in data["chunks"] if row["chunk_id"] == matches["sources"][0]["chunk_id"])
    assert matches["sources"][0]["snippet"] == expected["snippet"]
    assert "vector" not in matches["sources"][0]
    assert kb.retrieve("木星大红斑与木卫二", model)["status"] == "not_found"


def test_missing_or_stale_index_never_supplies_evidence(index):
    model = FixtureEmbeddings()
    assert kb.retrieve("主动降噪和被动隔音", model)["sources"] == []
    payload = kb.build_index(index, model)
    payload["source_sha256"] = "stale"
    index.write_text(json.dumps(payload), encoding="utf-8")
    assert kb.knowledge_status()["status"] == "unavailable"
    assert kb.retrieve("主动降噪和被动隔音", model)["sources"] == []


def test_offline_graph_evaluation():
    results = run_cases("offline")
    assert len(results) >= 20
    assert all(result["ok"] for result in results), [row for row in results if not row["ok"]]
