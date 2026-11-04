import json


def test_chat(client):
    resp = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "你好，介绍一下你自己"}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "MOCK" in body["content"]
    assert body["mode"] == "mock"
    assert body["usage"]["total_tokens"] > 0


def test_chat_validation(client):
    resp = client.post("/api/v1/chat", json={"messages": []})
    assert resp.status_code == 422


def test_chat_stream(client):
    with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"messages": [{"role": "user", "content": "流式测试"}]},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = [
            json.loads(line[6:])
            for line in resp.iter_lines()
            if line.startswith("data: ")
        ]

    kinds = [event["type"] for event in events]
    assert "delta" in kinds
    assert kinds[-1] == "done"
    assert events[-1]["mode"] == "mock"
    text = "".join(event["delta"] for event in events if event["type"] == "delta")
    assert "MOCK" in text
