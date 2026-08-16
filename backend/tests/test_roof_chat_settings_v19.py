from __future__ import annotations

import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./data/test_roof_chat_settings_v19.db"
os.environ["SECRET_KEY"] = "roof-test-secret-key"

TEST_DB = Path(__file__).resolve().parents[1] / "data" / "test_roof_chat_settings_v19.db"
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


def _invoke(
    client: TestClient,
    token: str,
    method: str,
    params: dict | None = None,
    expected: int = 200,
):
    response = client.post(
        "/api/roof/invoke",
        headers={"Authorization": f"Bearer {token}"},
        json={"method": method, "params": params or {}},
    )
    assert response.status_code == expected, response.text
    return response.json()


def test_group_settings_admin_rights_hidden_members_and_posting_mode() -> None:
    with TestClient(app) as client:
        owner_token, owner = _register(client, "settings-owner@example.com")
        admin_token, admin = _register(client, "settings-admin@example.com")
        member_token, member = _register(client, "settings-member@example.com")

        created = _invoke(
            client,
            owner_token,
            "messages.createChat",
            {
                "title": "Roof Team",
                "users": [
                    {"_": "inputUser", "user_id": admin["id"], "access_hash": "0"},
                    {"_": "inputUser", "user_id": member["id"], "access_hash": "0"},
                ],
            },
        )
        chat_id = created["chats"][0]["id"]

        settings = _invoke(
            client,
            owner_token,
            "roof.updateChatSettings",
            {
                "chat_id": chat_id,
                "title": "Roof Core Team",
                "about": "Internal Roof team",
                "hide_members": True,
                "history_visible": False,
                "posting_mode": "admins",
            },
        )
        assert settings["title"] == "Roof Core Team"
        assert settings["about"] == "Internal Roof team"
        assert settings["hide_members"] is True
        assert settings["history_visible"] is False
        assert settings["posting_mode"] == "admins"

        rights = {
            "change_info": True,
            "delete_messages": True,
            "pin_messages": True,
            "invite_users": True,
            "ban_users": False,
            "add_admins": False,
            "post_messages": True,
            "edit_messages": True,
            "manage_call": False,
        }
        updated = _invoke(
            client,
            owner_token,
            "roof.setMemberAdmin",
            {
                "chat_id": chat_id,
                "user_id": admin["id"],
                "enabled": True,
                "rank": "Moderator",
                "rights": rights,
            },
        )
        admin_row = next(row for row in updated["members"] if row["user"]["id"] == admin["id"])
        assert admin_row["role"] == "admin"
        assert admin_row["rank"] == "Moderator"
        assert admin_row["rights"]["ban_users"] is False
        assert admin_row["rights"]["delete_messages"] is True

        hidden_for_member = _invoke(client, member_token, "roof.getChatSettings", {"chat_id": chat_id})
        assert hidden_for_member["members"] == []

        denied = client.post(
            "/api/roof/invoke",
            headers={"Authorization": f"Bearer {member_token}"},
            json={
                "method": "messages.sendMessage",
                "params": {
                    "peer": {"_": "inputPeerChat", "chat_id": chat_id},
                    "message": "member should be blocked",
                    "random_id": "19001",
                },
            },
        )
        assert denied.status_code == 403, denied.text

        allowed = _invoke(
            client,
            admin_token,
            "messages.sendMessage",
            {
                "peer": {"_": "inputPeerChat", "chat_id": chat_id},
                "message": "admin can post",
                "random_id": "19002",
            },
        )
        assert allowed["updates"][0]["message"]["message"] == "admin can post"

        first_link = settings["invite_link"]
        reset = _invoke(client, owner_token, "roof.resetInviteLink", {"chat_id": chat_id})
        assert reset["invite_link"] != first_link


def test_channel_privacy_comments_avatar_member_removal_and_delete() -> None:
    with TestClient(app) as client:
        owner_token, owner = _register(client, "channel-owner-v19@example.com")
        member_token, member = _register(client, "channel-member-v19@example.com")

        created = _invoke(
            client,
            owner_token,
            "channels.createChannel",
            {"title": "Roof News", "about": "Initial"},
        )
        chat_id = created["chats"][0]["id"]

        _invoke(
            client,
            owner_token,
            "channels.inviteToChannel",
            {
                "channel": {"_": "inputChannel", "channel_id": chat_id, "access_hash": "0"},
                "users": [{"_": "inputUser", "user_id": member["id"], "access_hash": "0"}],
            },
        )

        settings = _invoke(
            client,
            owner_token,
            "roof.updateChatSettings",
            {
                "chat_id": chat_id,
                "about": "Public Roof channel",
                "is_public": True,
                "username": "roof_news_v19",
                "comments_enabled": True,
                "hide_members": True,
                "avatar_url": "/uploads/fake-channel-avatar.png",
            },
        )
        assert settings["is_public"] is True
        assert settings["username"] == "roof_news_v19"
        assert settings["comments_enabled"] is True
        assert settings["hide_members"] is True
        assert settings["avatar_url"] == "/uploads/fake-channel-avatar.png"
        assert settings["posting_mode"] == "admins"

        member_view = _invoke(client, member_token, "roof.getChatSettings", {"chat_id": chat_id})
        assert member_view["members"] == []

        removed = _invoke(
            client,
            owner_token,
            "roof.removeMember",
            {"chat_id": chat_id, "user_id": member["id"]},
        )
        assert all(row["user"]["id"] != member["id"] for row in removed["members"])

        deleted = _invoke(client, owner_token, "roof.deleteChat", {"chat_id": chat_id})
        assert deleted is True

        missing = client.post(
            "/api/roof/invoke",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"method": "roof.getChatSettings", "params": {"chat_id": chat_id}},
        )
        assert missing.status_code == 404, missing.text
