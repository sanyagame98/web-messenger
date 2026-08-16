from __future__ import annotations

import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./data/test_roof_direct_chat_v16.db"
os.environ["SECRET_KEY"] = "roof-test-secret-key"

TEST_DB = Path(__file__).resolve().parents[1] / "data" / "test_roof_direct_chat_v16.db"
TEST_DB.unlink(missing_ok=True)

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


def _invoke(client: TestClient, token: str, method: str, params: dict | None = None):
    response = client.post(
        "/api/roof/invoke",
        headers={"Authorization": f"Bearer {token}"},
        json={"method": method, "params": params or {}},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_direct_chat_username_search_open_contacts_and_read() -> None:
    with TestClient(app) as client:
        alice_token, alice = _register(client, "v16-alice@example.com")
        bob_token, bob = _register(client, "v16-bob@example.com")

        renamed = _invoke(
            client,
            bob_token,
            "account.updateUsername",
            {"username": "roof_bob_v16"},
        )
        assert renamed["username"] == "roof_bob_v16"

        search = _invoke(
            client,
            alice_token,
            "contacts.search",
            {"q": "@roof_bob", "limit": 20},
        )
        assert search["users"][0]["id"] == bob["id"]
        assert search["users"][0]["username"] == "roof_bob_v16"

        resolved = _invoke(
            client,
            alice_token,
            "contacts.resolveUsername",
            {"username": "@roof_bob_v16"},
        )
        assert resolved["peer"]["user_id"] == bob["id"]

        opened = _invoke(
            client,
            alice_token,
            "roof.openDirectChat",
            {"username": "roof_bob_v16"},
        )
        assert opened["_"] == "messages.peerDialogs"
        assert opened["dialogs"][0]["peer"]["user_id"] == bob["id"]

        contacts = _invoke(client, alice_token, "contacts.getContacts")
        assert any(item["user_id"] == bob["id"] for item in contacts["contacts"])
        assert any(user["id"] == bob["id"] for user in contacts["users"])

        sent = _invoke(
            client,
            alice_token,
            "messages.sendMessage",
            {
                "peer": {"_": "inputPeerUser", "user_id": bob["id"], "access_hash": "0"},
                "message": "real direct chat",
                "random_id": "16001",
            },
        )
        message_id = sent["updates"][0]["message"]["id"]

        history = _invoke(
            client,
            bob_token,
            "messages.getHistory",
            {
                "peer": {"_": "inputPeerUser", "user_id": alice["id"], "access_hash": "0"},
                "limit": 20,
            },
        )
        assert history["messages"][0]["message"] == "real direct chat"

        read = _invoke(
            client,
            bob_token,
            "messages.readHistory",
            {
                "peer": {"_": "inputPeerUser", "user_id": alice["id"], "access_hash": "0"},
                "max_id": message_id,
            },
        )
        assert read["_"] == "messages.affectedMessages"
        assert read["pts"] == message_id
