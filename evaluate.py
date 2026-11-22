"""在隔离的 SQLite 中运行公开可复现的模拟数据评估。"""
import argparse
import json
import os
import re
import statistics
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch

import httpx

import knowledge_index as kb
import model_client

CASES = Path(__file__).with_name("evaluation_cases.json")


class FixtureEmbeddings:
    """仅供评估与测试，用词项映射稳定向量；线上索引不使用它。"""
    vocabulary = ("主动降噪", "被动隔音", "反相", "退货", "申请条件", "7 个自然日", "木星", "木卫二")

    def encode(self, text):
        return [float(word in text) for word in self.vocabulary] + [0.01]

    def passage_embed(self, texts, batch_size=16):
        return map(self.encode, texts)

    def query_embed(self, text):
        yield self.encode(text)


def fake_provider(turn, request):
    messages = json.loads(request.content)["messages"]
    last = messages[-1]
    if last["role"] == "user" and turn["calls"]:
        if turn.get("followup"):
            assert any(item["role"] == "tool" and turn["followup"] in item["content"] for item in messages)
        assistant = {"role": "assistant", "content": None, "tool_calls": [
            {"id": f"fixture_call_{index}", "type": "function", "function": {
                "name": name, "arguments": json.dumps(args, ensure_ascii=False)}}
            for index, (name, args) in enumerate(turn["calls"])]}
    else:
        if turn.get("upstream_failure"):
            return httpx.Response(503, json={"error": {"message": "fixture model unavailable"}})
        calls = []
        if last["role"] == "tool":
            for item in reversed(messages):
                if item["role"] != "tool":
                    assert {tool["id"] for tool in item["tool_calls"]} == {tool["tool_call_id"] for tool in calls}
                    break
                calls.append(item)
        assistant = {"role": "assistant", "content": turn.get("reply") or (
            "\n".join(item["content"] for item in reversed(calls)) or "你好！")}
    return httpx.Response(200, json={"id": "fixture", "model": "fixture", "created": 1,
        "object": "chat.completion", "choices": [{"index": 0, "message": assistant,
        "finish_reason": "tool_calls" if assistant.get("tool_calls") else "stop"}]})


def check(turn, result, observed, source_index, client):
    assert {name for name, _ in turn["calls"]} <= set(observed), observed
    if not turn["calls"]:
        assert not observed, observed
    if "products" in turn:
        assert [item["id"] for item in result["products"]] == turn["products"]
    if "favorites" in turn:
        assert result["favorite_ids"] == turn["favorites"]
    if turn.get("contains"):
        assert turn["contains"] in result["reply"], result["reply"]
    if turn.get("excludes"):
        assert turn["excludes"] not in result["reply"]
    sources = result["sources"]
    for source in sources:
        assert source_index[source["chunk_id"]] == source
    if turn.get("source"):
        assert turn["source"] in {source["id"] for source in sources}, sources
    if turn.get("sources_empty"):
        assert not sources
    if turn.get("has_products"):
        assert result["products"]
    if turn.get("history"):
        history = client.get("/api/conversations/" + result["session_id"]).json()
        assert history["turns"][-1]["sources"] == sources
    if turn.get("unsaved"):
        assert client.get("/api/conversations").json()["items"] == []


def run_cases(mode):
    from fastapi.testclient import TestClient
    import main as app_module
    from storage import Store
    from tracing import TurnTrace

    original = model_client.create_chat_model
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    results = []
    with TemporaryDirectory() as temporary, ExitStack() as stack:
        root = Path(temporary)
        local_index = root / "fixture.json"
        if mode == "offline":
            stack.enter_context(patch.dict(os.environ, {"OPENAI_API_KEY": "fixture-only", "OPENAI_MODEL": "fixture",
                                                       "OPENAI_BASE_URL": "https://api.deepseek.com"}))
            retriever = kb.retrieve
            stack.enter_context(patch.object(kb, "retrieve", lambda query: retriever(query, FixtureEmbeddings())))
            kb.build_index(local_index, FixtureEmbeddings())
        stack.enter_context(patch.dict(os.environ, {"SHOP_LANGSMITH_TRACING": "false"}))
        source_index = {}
        source_path = local_index if mode == "offline" else kb.index_path()
        if source_path.exists():
            source_index = {item["chunk_id"]: {key: value for key, value in item.items() if key != "vector"}
                            for item in json.loads(source_path.read_text(encoding="utf-8"))["chunks"]}

        for case in cases:
            if mode == "live" and case.get("mode") == "offline":
                continue
            start = perf_counter()
            store = Store(root / (case["id"] + ".sqlite3"), 1)
            error = None
            session = None
            with ExitStack() as scoped:
                scoped.enter_context(patch.dict(app_module.app.dependency_overrides, {app_module.get_store: lambda: store}))
                if mode == "offline":
                    path = root / "missing.json" if case.get("no_index") else local_index
                    scoped.enter_context(patch.dict(os.environ, {"SHOP_KB_INDEX": str(path), "SHOP_KB_MIN_SCORE": "0.65"}))
                client = scoped.enter_context(TestClient(app_module.app))
                for turn in case["turns"]:
                    observed = []
                    previous_record = TurnTrace.record

                    def record(trace, name, started, outcome):
                        if name in turn_tool_names:
                            observed.append(name)
                        return previous_record(trace, name, started, outcome)

                    turn_tool_names = {"search_products", "get_product_detail", "list_coupons",
                                       "query_order", "manage_favorites", "retrieve_knowledge"}
                    if turn.get("new_visitor"):
                        client.cookies.clear()
                        session = None
                    with ExitStack() as per_turn:
                        per_turn.enter_context(patch.object(TurnTrace, "record", record))
                        if mode == "offline":
                            transport = httpx.MockTransport(lambda req: fake_provider(turn, req))
                            per_turn.enter_context(patch.object(model_client, "create_chat_model",
                                lambda: original(httpx.Client(transport=transport))))
                        try:
                            response = client.post("/chat", json={"message": turn["ask"], "session_id": session})
                            if turn.get("upstream_failure"):
                                assert response.status_code == 503
                                assert client.get("/api/conversations").json()["items"] == []
                                continue
                            assert response.status_code == 200, response.text
                            result = response.json()
                            check(turn, result, observed, source_index, client)
                            session = result["session_id"] if result.get("turn_status") == "completed" else session
                        except Exception as exc:
                            error = str(exc) or type(exc).__name__
                            break
            results.append({"id": case["id"], "ok": error is None, "ms": round((perf_counter() - start) * 1000, 1),
                            **({"error": error} if error else {})})
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["offline", "live"], default="offline")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mode == "live" and (not os.getenv("OPENAI_API_KEY") or not os.getenv("OPENAI_MODEL")):
        parser.error("live 模式需要在本机设置 OPENAI_API_KEY、OPENAI_MODEL、OPENAI_BASE_URL，并先构建索引")
    results = run_cases(args.mode)
    passed = sum(result["ok"] for result in results)
    report = {"mode": args.mode, "model_network": args.mode == "live", "passed": passed,
              "total": len(results), "pass_rate": round(passed / len(results), 4),
              "median_ms": statistics.median(row["ms"] for row in results), "cases": results}
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)
    raise SystemExit(passed != len(results))


if __name__ == "__main__":
    main()
