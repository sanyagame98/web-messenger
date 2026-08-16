from __future__ import annotations

import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./data/test_roof_channel_discussions_v20.db"
os.environ["SECRET_KEY"] = "roof-test-secret-key"

TEST_DB = Path(__file__).resolve().parents[1] / "data" / "test_roof_channel_discussions_v20.db"
TEST_DB.unlink(missing_ok=True)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def _register(client: TestClient, email: str) -> tuple[str, dict]:
    response = client.post("/api/auth/register", json={"email": email, "password": "roofpass123"})
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


def test_channel_post_discussion_join_reply_reaction_and_count() -> None:
    with TestClient(app) as client:
        owner_token, owner = _register(client, "discussion-owner@example.com")
        member_token, member = _register(client, "discussion-member@example.com")

        created = _invoke(
            client,
            owner_token,
            "channels.createChannel",
            {"title": "Roof News", "about": "Channel discussions"},
        )
        channel_id = created["chats"][0]["id"]

        _invoke(
            client,
            owner_token,
            "channels.inviteToChannel",
            {
                "channel": {"_": "inputChannel", "channel_id": channel_id, "access_hash": "0"},
                "users": [{"_": "inputUser", "user_id": member["id"], "access_hash": "0"}],
            },
        )
        settings = _invoke(
            client,
            owner_token,
            "roof.updateChatSettings",
            {"chat_id": channel_id, "comments_enabled": True},
        )
        assert settings["comments_enabled"] is True

        sent = _invoke(
            client,
            owner_token,
            "messages.sendMessage",
            {
                "peer": {"_": "inputPeerChannel", "channel_id": channel_id, "access_hash": "0"},
                "message": "Post with real Roof comments",
                "random_id": "20001",
            },
        )
        post_id = sent["updates"][0]["message"]["id"]

        initial = _invoke(
            client,
            member_token,
            "roof.getPostDiscussion",
            {"channel_id": channel_id, "post_id": post_id},
        )
        assert initial["count"] == 0
        assert initial["joined"] is False

        joined = _invoke(
            client,
            member_token,
            "roof.joinPostDiscussion",
            {"channel_id": channel_id, "post_id": post_id},
        )
        assert joined["joined"] is True

        first = _invoke(
            client,
            member_token,
            "roof.sendPostComment",
            {"channel_id": channel_id, "post_id": post_id, "message": "First comment"},
        )
        assert first["message"] == "First comment"

        reply = _invoke(
            client,
            owner_token,
            "roof.sendPostComment",
            {
                "channel_id": channel_id,
                "post_id": post_id,
                "message": "Reply from owner",
                "reply_to": first["id"],
            },
        )
        assert reply["reply_to"] == first["id"]

        reaction = _invoke(
            client,
            member_token,
            "roof.reactPostComment",
            {
                "channel_id": channel_id,
                "post_id": post_id,
                "comment_id": reply["id"],
                "emoji": "🔥",
            },
        )
        assert reaction["reactions"][0]["emoji"] == "🔥"
        assert reaction["reactions"][0]["count"] == 1

        counts = _invoke(
            client,
            member_token,
            "roof.getPostCommentCounts",
            {"channel_id": channel_id, "post_ids": [post_id]},
        )
        assert counts["counts"][str(post_id)] == 2

        final = _invoke(
            client,
            owner_token,
            "roof.getPostDiscussion",
            {"channel_id": channel_id, "post_id": post_id},
        )
        assert final["count"] == 2
        assert final["comments"][1]["reply_to"] == first["id"]
