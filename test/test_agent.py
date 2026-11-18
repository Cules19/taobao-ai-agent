import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import OpenAI

import agent
import main
import model_client
from sessions import Session
from shop_tools import execute_tool


def completion(message):
    return {"id": "test-response", "object": "chat.completion", "created": 1,
            "model": "test-model", "choices": [{"index": 0, "message": message,
                      "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}]}


def call(name, arguments, call_id="call_1"):
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": call_id, "type": "function", "function": {
            "name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}]}


@pytest.fixture
def provider(monkeypatch):
    requests = []

    def install(*replies):
        responses = iter(replies)

        def respond(request):
            assert request.url.path == "/chat/completions"
            requests.append(json.loads(request.content))
            reply = next(responses)
            if callable(reply):
                reply = reply(requests[-1])
            if isinstance(reply, httpx.Response):
                return reply
            return httpx.Response(200, json=completion(reply))

        def new_client():
            transport = httpx.MockTransport(respond)
            return OpenAI(api_key="test-only", base_url="https://api.deepseek.com",
                          http_client=httpx.Client(transport=transport)), "test-model"

        monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")
        monkeypatch.setattr(model_client, "create_model_client", new_client)
        return requests

    return install


def test_sdk_tool_round_trip_and_session_history(provider):
    def verify_search(request):
        assistant, tool = request["messages"][-2:]
        assert assistant["tool_calls"][0]["id"] == tool["tool_call_id"] == "call_search"
        products = json.loads(tool["content"])["products"]
        assert [item["id"] for item in products] == ["P102", "P101", "P103"]
        return {"role": "assistant", "content": "第一款是 P102。"}

    def verify_followup(request):
        messages = request["messages"]
        assert [message["role"] for message in messages] == [
            "system", "user", "assistant", "tool", "assistant", "user"]
        assert "200" in messages[1]["content"]
        assert "P102" in messages[4]["content"]
        return call("get_product_detail", {"product_id": "P102"}, "call_detail")

    requests = provider(call("search_products", {"category": "耳机", "keyword": "蓝牙",
                                                "max_price": 200, "sort_by": "sales_desc"}, "call_search"),
                        verify_search, verify_followup, {"role": "assistant", "content": "黑色和蓝色。"})
    client = TestClient(main.app)
    first = client.post("/chat", json={"message": "200元内的蓝牙耳机，按销量排序"})
    assert first.status_code == 200
    assert requests[0]["thinking"] == {"type": "disabled"}
    assert requests[0]["tool_choice"] == "auto"
    assert {tool["function"]["name"] for tool in requests[0]["tools"]} == {
        "search_products", "get_product_detail", "list_coupons", "query_order", "manage_favorites"}
    second = client.post("/chat", json={"message": "第一款还有什么颜色？",
                                       "session_id": first.json()["session_id"]})
    assert second.json()["session_id"] == first.json()["session_id"]
    assert second.json()["products"][0]["stock"] == 83
    assert second.json()["reply"] == "黑色和蓝色。"


def test_failed_search_returns_grounded_fallback(provider):
    def verify_empty(request):
        assert json.loads(request["messages"][-1]["content"])["status"] == "not_found"
        return {"role": "assistant", "content": "可以买一款无中生有的耳机。"}

    provider(call("search_products", {"category": "耳机", "max_price": 1}), verify_empty)
    result = agent.run_turn("一元以内的耳机", Session())
    assert "没有符合条件" in result["reply"]
    assert "无中生有" not in result["reply"]
    assert result["products"] == []


def test_favorites_and_context_do_not_leak_to_new_session(provider):
    def check_new_session(request):
        assert [message["role"] for message in request["messages"]] == ["system", "user"]
        return call("manage_favorites", {"action": "list"})

    yes = {"role": "assistant", "content": "已处理。"}
    provider(call("manage_favorites", {"action": "add", "product_id": "P102"}), yes,
             check_new_session, yes)
    client = TestClient(main.app)
    first = client.post("/chat", json={"message": "收藏 P102"}).json()
    second = client.post("/chat", json={"message": "我的收藏"}).json()
    assert first["favorite_ids"] == ["P102"]
    assert second["session_id"] != first["session_id"]
    assert second["favorite_ids"] == []
    assert "还没有收藏" in second["reply"]


def test_loop_limit_does_not_commit_partial_turn(provider):
    requests = provider(*[call("manage_favorites", {"action": "add", "product_id": "P102"},
                               f"call_{index}") for index in range(agent.MAX_MODEL_REQUESTS)])
    session = Session()
    assert agent.run_turn("收藏 P102", session)["reply"] == agent.LIMIT_REPLY
    assert len(requests) == agent.MAX_MODEL_REQUESTS
    assert not session.turns and not session.favorites


def test_provider_error_does_not_leak_error_body(provider):
    provider(httpx.Response(401, json={"error": {"message": "private provider detail"}}))
    response = TestClient(main.app).post("/chat", json={"message": "你好"})
    assert response.status_code == 503
    assert response.json() == {"detail": "模型服务暂时不可用"}


def test_parameter_validation_and_log_redaction(caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error.shop_tools")
    assert "DEMO1001" in execute_tool("query_order", "{}", [])["message"]
    assert execute_tool("search_products", '{"max_price":"100"}', [])["status"] == "invalid"
    assert execute_tool("search_products", '{"keyword":"secret-text","max_price":100}', [])["status"] == "not_found"
    assert execute_tool("unknown_tool", "{}", [])["status"] == "error"
    assert "elapsed_ms=" in caplog.text and "max_price" in caplog.text
    assert "secret-text" not in caplog.text


def test_tool_exception_returns_safe_result(monkeypatch):
    import shop_tools

    def fail(**kwargs):
        raise OSError("internal path")

    schema, _, description = shop_tools.TOOL_REGISTRY["query_order"]
    monkeypatch.setitem(shop_tools.TOOL_REGISTRY, "query_order", (schema, fail, description))
    assert execute_tool("query_order", '{"order_id":"DEMO1001"}', []) == {
        "status": "error", "message": "工具暂时不可用，请稍后再试。"}
