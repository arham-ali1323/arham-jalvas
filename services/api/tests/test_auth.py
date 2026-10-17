from tests.conftest import register


async def test_register_and_me(client):
    tokens = await register(client)
    assert tokens["access_token"] and tokens["refresh_token"]

    me = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == "user@example.com"


async def test_duplicate_email_rejected(client):
    await register(client)
    resp = await client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "supersecret1"},
    )
    assert resp.status_code == 409


async def test_login_and_wrong_password(client):
    await register(client)
    ok = await client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "supersecret1"},
    )
    assert ok.status_code == 200

    bad = await client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "wrong-password"},
    )
    assert bad.status_code == 401


async def test_me_requires_token(client):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


async def test_refresh_issues_new_tokens(client):
    tokens = await register(client)
    resp = await client.post(
        "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_password_reset_flow(client, monkeypatch):
    await register(client)

    captured = {}

    def fake_send(to, subject, body):
        captured["to"] = to
        captured["body"] = body

    monkeypatch.setattr("app.routes.auth.send_email", fake_send)

    resp = await client.post(
        "/auth/password-reset/request", json={"email": "user@example.com"}
    )
    assert resp.status_code == 202
    assert "token=" in captured["body"]
    token = captured["body"].split("token=")[1].split()[0].strip()

    confirm = await client.post(
        "/auth/password-reset/confirm",
        json={"token": token, "new_password": "brandnewpass9"},
    )
    assert confirm.status_code == 200

    # New password works, old one no longer does.
    new_login = await client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "brandnewpass9"},
    )
    assert new_login.status_code == 200
    old_login = await client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "supersecret1"},
    )
    assert old_login.status_code == 401
