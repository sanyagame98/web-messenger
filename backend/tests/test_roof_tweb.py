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


def _invoke_response(
    client: TestClient,
    token: str,
    method: str,
    params: dict | None = None,
):
    return client.post(
        "/api/roof/invoke",
        headers={"Authorization": f"Bearer {token}"},
        json={"method": method, "params": params or {}},
    )


def _invoke(client: TestClient, token: str, method: str, params: dict | None = None):
    response = _invoke_response(client, token, method, params)
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


def test_roof_tweb_profile_group_and_startup_api() -> None:
    with TestClient(app) as client:
        owner_token, owner = _register(client, "owner.group@example.com")
        member_token, member = _register(client, "member.group@example.com")

        config = _invoke(client, owner_token, "help.getConfig")
        assert config["_"] == "config"
        assert config["dc_options"] == []
        app_config = _invoke(client, owner_token, "help.getAppConfig")
        assert app_config["config"]["reactions_user_max_default"] == 1

        profile = _invoke(
            client,
            owner_token,
            "account.updateProfile",
            {"first_name": "Roof", "last_name": "Owner", "about": "My Roof profile"},
        )
        assert profile["first_name"] == "Roof Owner"

        assert _invoke(
            client,
            owner_token,
            "account.checkUsername",
            {"username": "roof_group_owner"},
        ) is True
        renamed = _invoke(
            client,
            owner_token,
            "account.updateUsername",
            {"username": "roof_group_owner"},
        )
        assert renamed["username"] == "roof_group_owner"

        created = _invoke(
            client,
            owner_token,
            "messages.createChat",
            {
                "title": "Roof Test Group",
                "users": [
                    {"_": "inputUser", "user_id": member["id"], "access_hash": "0"}
                ],
            },
        )
        assert created["chats"][0]["title"] == "Roof Test Group"
        chat_id = created["chats"][0]["id"]

        full = _invoke(client, owner_token, "messages.getFullChat", {"chat_id": chat_id})
        assert len(full["full_chat"]["participants"]["participants"]) == 2

        sent = _invoke(
            client,
            owner_token,
            "messages.sendMessage",
            {
                "peer": {"_": "inputPeerChat", "chat_id": chat_id},
                "message": "hello group",
                "random_id": "2",
            },
        )
        assert sent["updates"][0]["message"]["message"] == "hello group"

        member_dialogs = _invoke(client, member_token, "messages.getDialogs", {"limit": 20})
        assert any(chat["id"] == chat_id for chat in member_dialogs["chats"])

        edited = _invoke(
            client,
            owner_token,
            "messages.editChatTitle",
            {"chat_id": chat_id, "title": "Roof Renamed Group"},
        )
        assert edited["chats"][0]["title"] == "Roof Renamed Group"
        assert owner["id"] != member["id"]


def test_roof_tweb_channel_permissions_edit_and_delete() -> None:
    with TestClient(app) as client:
        owner_token, owner = _register(client, "owner.channel@example.com")
        member_token, member = _register(client, "member.channel@example.com")

        created = _invoke(
            client,
            owner_token,
            "channels.createChannel",
            {"title": "Roof News", "about": "Roof channel", "broadcast": True},
        )
        channel = created["chats"][0]
        assert channel["_"] == "channel"
        channel_id = channel["id"]

        invited = _invoke(
            client,
            owner_token,
            "channels.inviteToChannel",
            {
                "channel": {"_": "inputChannel", "channel_id": channel_id, "access_hash": "0"},
                "users": [
                    {"_": "inputUser", "user_id": member["id"], "access_hash": "0"}
                ],
            },
        )
        assert len(invited["users"]) == 2

        sent = _invoke(
            client,
            owner_token,
            "messages.sendMessage",
            {
                "peer": {"_": "inputPeerChannel", "channel_id": channel_id, "access_hash": "0"},
                "message": "Roof channel post",
                "random_id": "3",
            },
        )
        message_id = sent["updates"][0]["message"]["id"]
        assert sent["updates"][0]["message"]["peer_id"]["_"] == "peerChannel"

        forbidden = _invoke_response(
            client,
            member_token,
            "messages.sendMessage",
            {
                "peer": {"_": "inputPeerChannel", "channel_id": channel_id, "access_hash": "0"},
                "message": "subscriber cannot post",
                "random_id": "4",
            },
        )
        assert forbidden.status_code == 403

        edited = _invoke(
            client,
            owner_token,
            "messages.editMessage",
            {
                "peer": {"_": "inputPeerChannel", "channel_id": channel_id, "access_hash": "0"},
                "id": message_id,
                "message": "Roof edited post",
            },
        )
        assert edited["updates"][0]["message"]["message"] == "Roof edited post"

        history = _invoke(
            client,
            member_token,
            "messages.getHistory",
            {
                "peer": {"_": "inputPeerChannel", "channel_id": channel_id, "access_hash": "0"},
                "limit": 20,
            },
        )
        assert history["messages"][0]["message"] == "Roof edited post"
        assert history["chats"][0]["_"] == "channel"

        deleted = _invoke(
            client,
            owner_token,
            "messages.deleteMessages",
            {"id": [message_id], "revoke": True},
        )
        assert deleted["pts_count"] == 1

        empty_history = _invoke(
            client,
            member_token,
            "messages.getHistory",
            {
                "peer": {"_": "inputPeerChannel", "channel_id": channel_id, "access_hash": "0"},
                "limit": 20,
            },
        )
        assert empty_history["messages"] == []

        dialogs = _invoke(client, member_token, "messages.getDialogs", {"limit": 20})
        assert any(chat["id"] == channel_id and chat["_"] == "channel" for chat in dialogs["chats"])
        assert owner["id"] != member["id"]
