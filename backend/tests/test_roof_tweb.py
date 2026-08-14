from __future__ import annotations

import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./data/test_roof_tweb.db"
os.environ["SECRET_KEY"] = "roof-test-secret-key"

TEST_DB = Path(__file__).resolve().parents[1] / "data" / "test_roof_tweb.db"
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


def test_roof_tweb_email_chat_flow() -> None:
    with TestClient(app) as client:
        alice_token, alice = _register(client, "alice.roof@example.com")
        bob_token, bob = _register(client, "bob.roof@example.com")

        search = _invoke(
            client,
            alice_token,
            "contacts.search",
            {"q": bob["username"], "limit": 20},
        )
        assert any(user["id"] == bob["id"] for user in search["users"])

        sent = _invoke(
            client,
            alice_token,
            "messages.sendMessage",
            {
                "peer": {"_": "inputPeerUser", "user_id": bob["id"], "access_hash": "0"},
                "message": "hello from Roof",
                "random_id": "1",
            },
        )
        assert sent["_"] == "updates"
        assert sent["updates"][0]["message"]["message"] == "hello from Roof"

        dialogs = _invoke(client, bob_token, "messages.getDialogs", {"limit": 20})
        assert len(dialogs["dialogs"]) == 1
        assert dialogs["messages"][0]["message"] == "hello from Roof"

        history = _invoke(
            client,
            bob_token,
            "messages.getHistory",
            {
                "peer": {"_": "inputPeerUser", "user_id": alice["id"], "access_hash": "0"},
                "limit": 50,
            },
        )
        assert [message["message"] for message in history["messages"]] == ["hello from Roof"]
        assert history["messages"][0]["pFlags"] == {}

        me = _invoke(
            client,
            alice_token,
            "users.getFullUser",
            {"id": {"_": "inputUserSelf"}},
        )
        assert me["users"][0]["id"] == alice["id"]
