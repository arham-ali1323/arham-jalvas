async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


async def test_ready_hits_database(client):
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


async def test_root(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "service" in resp.json()
