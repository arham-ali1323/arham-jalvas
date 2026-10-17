import json

from tests.conftest import register


def _auth(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_streaming_completion_and_persistence(client):
    tokens = await register(client)
    resp = await client.post(
        "/chat/completions",
        json={"message": "Hi there"},
        headers=_auth(tokens),
    )
    assert resp.status_code == 200
    assert "data:" in resp.text
    assert "Hello" in resp.text
    assert "[DONE]" in resp.text

    # The conversation and both turns must be persisted.
    convs = await client.get("/conversations", headers=_auth(tokens))
    assert convs.status_code == 200
    assert len(convs.json()) == 1
    conv_id = convs.json()[0]["id"]

    detail = await client.get(f"/conversations/{conv_id}", headers=_auth(tokens))
    assert detail.status_code == 200
    messages = detail.json()["messages"]
    roles = [m["role"] for m in messages]
    assert roles == ["user", "assistant"]
    assert messages[1]["content"] == "Hello, world"


async def test_conversations_are_isolated_between_users(client):
    alice = await register(client, email="alice@example.com")
    bob = await register(client, email="bob@example.com")

    await client.post(
        "/chat/completions", json={"message": "secret"}, headers=_auth(alice)
    )
    alice_convs = (await client.get("/conversations", headers=_auth(alice))).json()
    conv_id = alice_convs[0]["id"]

    # Bob must not be able to read Alice's conversation.
    resp = await client.get(f"/conversations/{conv_id}", headers=_auth(bob))
    assert resp.status_code == 404

    bobs_list = (await client.get("/conversations", headers=_auth(bob))).json()
    assert bobs_list == []


async def test_providers_endpoint(client):
    tokens = await register(client)
    resp = await client.get("/chat/providers", headers=_auth(tokens))
    assert resp.status_code == 200
    body = resp.json()
    assert body and body[0]["name"] == "gemini"


async def test_continue_existing_conversation(client):
    tokens = await register(client)
    first = await client.post(
        "/chat/completions", json={"message": "one"}, headers=_auth(tokens)
    )
    conv_id = json.loads(
        [l for l in first.text.splitlines() if '"done"' in l][0][6:]
    )["conversation_id"]

    second = await client.post(
        "/chat/completions",
        json={"message": "two", "conversation_id": conv_id},
        headers=_auth(tokens),
    )
    assert second.status_code == 200

    detail = await client.get(f"/conversations/{conv_id}", headers=_auth(tokens))
    roles = [m["role"] for m in detail.json()["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]
