from __future__ import annotations

import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./data/test_roof_channel_posts_v22.db"
os.environ["SECRET_KEY"] = "roof-test-secret-key"

TEST_DB = Path(__file__).resolve().parents[1] / "data" / "test_roof_channel_posts_v22.db"
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


def test_channel_post_views_author_mode_link_and_forward() -> None:
    with TestClient(app) as client:
        owner_token, owner = _register(client, "post-owner-v22@example.com")
        member_token, member = _register(client, "post-member-v22@example.com")

        created = _invoke(
            client,
            owner_token,
            "channels.createChannel",
            {"title": "Roof Post Lab", "about": "Real posts"},
        )
        channel_id = created["chats"][0]["id"]
        channel_peer = {"_": "inputPeerChannel", "channel_id": channel_id, "access_hash": "0"}

        _invoke(
            client,
            owner_token,
            "channels.inviteToChannel",
            {
                "channel": {"_": "inputChannel", "channel_id": channel_id, "access_hash": "0"},
                "users": [{"_": "inputUser", "user_id": member["id"], "access_hash": "0"}],
            },
        )
        _invoke(
            client,
            owner_token,
            "channels.updateUsername",
            {
                "channel": {"_": "inputChannel", "channel_id": channel_id, "access_hash": "0"},
                "username": "roofpost22",
            },
        )

        mode = _invoke(
            client,
            owner_token,
            "roof.setChannelPostingMode",
            {"channel_id": channel_id, "author_mode": "channel"},
        )
        assert mode["author_mode"] == "channel"

        anonymous = _invoke(
            client,
            owner_token,
            "messages.sendMessage",
            {"peer": channel_peer, "message": "Anonymous channel post", "random_id": "22001"},
        )
        anon_message = anonymous["updates"][0]["message"]
        anon_id = anon_message["id"]
        assert anon_message["pFlags"]["post"] is True
        assert anon_message["roof_post_author"]["mode"] == "channel"
        assert "from_id" not in anon_message
        assert anon_message["views"] == 0
        assert anon_message["roof_post_link"] == f"roof://roofpost22/{anon_id}"

        first_view = _invoke(
            client,
            member_token,
            "roof.markChannelPostViewed",
            {"channel_id": channel_id, "post_ids": [anon_id]},
        )
        assert first_view["counts"][str(anon_id)] == 1
        duplicate_view = _invoke(
            client,
            member_token,
            "roof.markChannelPostViewed",
            {"channel_id": channel_id, "post_ids": [anon_id]},
        )
        assert duplicate_view["counts"][str(anon_id)] == 1

        info = _invoke(
            client,
            owner_token,
            "roof.getChannelPostInfo",
            {"channel_id": channel_id, "post_id": anon_id},
        )
        assert info["views"] == 1
        assert info["author"]["mode"] == "channel"
        assert info["link"] == f"roof://roofpost22/{anon_id}"

        _invoke(
            client,
            owner_token,
            "roof.setChannelPostingMode",
            {"channel_id": channel_id, "author_mode": "admin"},
        )
        signed = _invoke(
            client,
            owner_token,
            "messages.sendMessage",
            {"peer": channel_peer, "message": "Signed admin post", "random_id": "22002"},
        )
        signed_message = signed["updates"][0]["message"]
        assert signed_message["roof_post_author"]["mode"] == "admin"
        assert signed_message["roof_post_author"]["user_id"] == owner["id"]
        assert signed_message["from_id"]["user_id"] == owner["id"]
        assert signed_message["post_author"]

        forwarded = _invoke(
            client,
            owner_token,
            "messages.forwardMessages",
            {
                "from_peer": channel_peer,
                "to_peer": {"_": "inputPeerUser", "user_id": member["id"], "access_hash": "0"},
                "id": [anon_id],
                "random_id": ["22003"],
            },
        )
        assert forwarded["updates"]
        assert forwarded["updates"][0]["message"]["message"] == "Anonymous channel post"
