from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/test_roof_tweb.db")
os.environ.setdefault("SECRET_KEY", "roof-test-secret-key")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def _register(client: TestClient, email: str) -> tuple[str, dict]:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "roofpass123"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    return data["access_token"], data["user"]


def _invoke(
    client: TestClient,
    token: str,
    method: str,
    params: dict | None = None,
):
    response = client.post(
        "/api/roof/invoke",
        headers={"Authorization": f"Bearer {token}"},
        json={"method": method, "params": params or {}},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_reply_forward_and_pin_flow() -> None:
    with TestClient(app) as client:
        alice_token, alice = _register(client, "features.alice@example.com")
        bob_token, bob = _register(client, "features.bob@example.com")
        alice_peer = {
            "_": "inputPeerUser",
            "user_id": alice["id"],
            "access_hash": "0",
        }
        bob_peer = {
            "_": "inputPeerUser",
            "user_id": bob["id"],
            "access_hash": "0",
        }

        original = _invoke(
            client,
            alice_token,
            "messages.sendMessage",
            {"peer": bob_peer, "message": "Roof original", "random_id": "101"},
        )
        original_id = original["updates"][0]["message"]["id"]

        reply = _invoke(
            client,
            bob_token,
            "messages.sendMessage",
            {
                "peer": alice_peer,
                "message": "Roof reply",
                "random_id": "102",
                "reply_to": {
                    "_": "inputReplyToMessage",
                    "reply_to_msg_id": original_id,
                },
            },
        )
        reply_message = reply["updates"][0]["message"]
        assert reply_message["reply_to"]["reply_to_msg_id"] == original_id

        _invoke(
            client,
            bob_token,
            "messages.updatePinnedMessage",
            {"peer": alice_peer, "id": original_id},
        )
        pinned = _invoke(
            client,
            bob_token,
            "messages.getPinnedHistory",
            {"peer": alice_peer, "limit": 20},
        )
        assert pinned["messages"][0]["id"] == original_id
        assert pinned["messages"][0]["pFlags"]["pinned"] is True

        group = _invoke(
            client,
            bob_token,
            "messages.createChat",
            {
                "title": "Roof Forward Test",
                "users": [
                    {
                        "_": "inputUser",
                        "user_id": alice["id"],
                        "access_hash": "0",
                    }
                ],
            },
        )
        group_id = group["chats"][0]["id"]
        group_peer = {"_": "inputPeerChat", "chat_id": group_id}

        forwarded = _invoke(
            client,
            bob_token,
            "messages.forwardMessages",
            {
                "from_peer": alice_peer,
                "id": [original_id],
                "random_id": ["103"],
                "to_peer": group_peer,
            },
        )
        forwarded_message = forwarded["updates"][0]["message"]
        assert forwarded_message["message"] == "Roof original"
        assert forwarded_message["fwd_from"]["from_id"]["user_id"] == alice["id"]

        group_history = _invoke(
            client,
            alice_token,
            "messages.getHistory",
            {"peer": group_peer, "limit": 20},
        )
        assert group_history["messages"][0]["fwd_from"]["from_id"]["user_id"] == alice["id"]

        _invoke(
            client,
            bob_token,
            "messages.unpinAllMessages",
            {"peer": alice_peer},
        )
        empty = _invoke(
            client,
            bob_token,
            "messages.getPinnedHistory",
            {"peer": alice_peer, "limit": 20},
        )
        assert empty["messages"] == []
