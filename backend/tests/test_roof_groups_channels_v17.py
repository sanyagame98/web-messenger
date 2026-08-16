from __future__ import annotations

import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./data/test_roof_groups_channels_v17.db"
os.environ["SECRET_KEY"] = "roof-test-secret-key"

TEST_DB = Path(__file__).resolve().parents[1] / "data" / "test_roof_groups_channels_v17.db"
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


def test_group_and_channel_creation_settings_persist() -> None:
    with TestClient(app) as client:
        owner_token, owner = _register(client, "v17-owner@example.com")
        _, member = _register(client, "v17-member@example.com")

        group = _invoke(
            client,
            owner_token,
            "messages.createChat",
            {
                "title": "Roof Friends",
                "users": [
                    {"_": "inputUser", "user_id": member["id"], "access_hash": "0"}
                ],
            },
        )
        group_id = group["chats"][0]["id"]
        assert group["chats"][0]["title"] == "Roof Friends"

        assert _invoke(
            client,
            owner_token,
            "messages.editChatAbout",
            {
                "peer": {"_": "inputPeerChat", "chat_id": group_id},
                "about": "Наша группа Roof",
            },
        ) is True

        group_full = _invoke(
            client,
            owner_token,
            "messages.getFullChat",
            {"chat_id": group_id},
        )
        assert group_full["full_chat"]["about"] == "Наша группа Roof"
        assert group_full["full_chat"]["exported_invite"]["link"].startswith("roof://join/")

        channel = _invoke(
            client,
            owner_token,
            "channels.createChannel",
            {
                "title": "Roof News",
                "about": "Новости Roof",
                "broadcast": True,
                "megagroup": False,
            },
        )
        channel_id = channel["chats"][0]["id"]
        assert channel["chats"][0]["title"] == "Roof News"

        channel_ref = {"_": "inputChannel", "channel_id": channel_id, "access_hash": "0"}
        assert _invoke(
            client,
            owner_token,
            "channels.checkUsername",
            {"channel": channel_ref, "username": "roof_news_v17"},
        ) is True
        assert _invoke(
            client,
            owner_token,
            "channels.updateUsername",
            {"channel": channel_ref, "username": "roof_news_v17"},
        ) is True

        invite = _invoke(
            client,
            owner_token,
            "messages.exportChatInvite",
            {"peer": {"_": "inputPeerChannel", "channel_id": channel_id, "access_hash": "0"}},
        )
        assert invite["link"].startswith("roof://join/")

        channel_full = _invoke(
            client,
            owner_token,
            "channels.getFullChannel",
            {"channel": channel_ref},
        )
        assert channel_full["full_chat"]["about"] == "Новости Roof"
        assert channel_full["chats"][0]["username"] == "roof_news_v17"
        assert channel_full["chats"][0]["pFlags"]["broadcast"] is True
        assert owner["id"] in [user["id"] for user in channel_full["users"]]
