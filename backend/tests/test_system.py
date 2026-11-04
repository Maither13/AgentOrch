def test_health(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["app"] == "AgentOrch"
    assert body["llm"]["mode"] == "mock"
    assert body["llm"]["configured"] is True


def test_models(client):
    resp = client.get("/api/v1/llm/models")
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()]
    assert "deepseek-chat" in ids


def test_ping(client):
    resp = client.post("/api/v1/llm/ping")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["mode"] == "mock"


def test_index_page(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "AgentOrch" in resp.text
