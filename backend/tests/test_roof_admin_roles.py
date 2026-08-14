from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _register(client: TestClient, email: str) -> tuple[str, dict]:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "roofpass123"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    return data["access_token"], data["user"]


def _request(
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
    response = _request(client, token, method, params)
    assert response.status_code == 200, response.text
    return response.json()


def _input_user(user: dict) -> dict:
    return {"_": "inputUser", "user_id": user["id"], "access_hash": "0"}


def test_roof_group_admin_permissions() -> None:
    with TestClient(app) as client:
        owner_token, owner = _register(client, "roles.group.owner@example.com")
        member_token, member = _register(client, "roles.group.member@example.com")
        outsider_token, outsider = _register(client, "roles.group.outsider@example.com")

        created = _invoke(
            client,
            owner_token,
            "messages.createChat",
            {"title": "Roof Staff", "users": [_input_user(member)]},
        )
        chat_id = created["chats"][0]["id"]

        denied = _request(
            client,
            member_token,
            "messages.editChatTitle",
            {"chat_id": chat_id, "title": "Nope"},
        )
        assert denied.status_code == 403

        assert _invoke(
            client,
            owner_token,
            "messages.editChatAdmin",
            {"chat_id": chat_id, "user_id": _input_user(member), "is_admin": True},
        ) is True

        renamed = _invoke(
            client,
            member_token,
            "messages.editChatTitle",
            {"chat_id": chat_id, "title": "Roof Staff Admin"},
        )
        assert renamed["chats"][0]["title"] == "Roof Staff Admin"

        added = _invoke(
            client,
            member_token,
            "messages.addChatUser",
            {"chat_id": chat_id, "user_id": _input_user(outsider), "fwd_limit": 100},
        )
        assert any(user["id"] == outsider["id"] for user in added["users"])

        cannot_remove_owner = _request(
            client,
            member_token,
            "messages.deleteChatUser",
            {"chat_id": chat_id, "user_id": _input_user(owner)},
        )
        assert cannot_remove_owner.status_code == 403

        full = _invoke(client, outsider_token, "messages.getFullChat", {"chat_id": chat_id})
        kinds = {item["user_id"]: item["_"] for item in full["full_chat"]["participants"]["participants"]}
        assert kinds[owner["id"]] == "chatParticipantCreator"
        assert kinds[member["id"]] == "chatParticipantAdmin"


def test_roof_channel_admin_and_subscriber_permissions() -> None:
    with TestClient(app) as client:
        owner_token, owner = _register(client, "roles.channel.owner@example.com")
        admin_token, admin = _register(client, "roles.channel.admin@example.com")
        member_token, member = _register(client, "roles.channel.member@example.com")

        created = _invoke(
            client,
            owner_token,
            "channels.createChannel",
            {"title": "Roof Updates", "about": "", "broadcast": True},
        )
        channel_id = created["chats"][0]["id"]
        channel = {"_": "inputChannel", "channel_id": channel_id, "access_hash": "0"}

        _invoke(
            client,
            owner_token,
            "channels.inviteToChannel",
            {"channel": channel, "users": [_input_user(admin), _input_user(member)]},
        )

        promoted = _invoke(
            client,
            owner_token,
            "channels.editAdmin",
            {
                "channel": channel,
                "user_id": _input_user(admin),
                "admin_rights": {
                    "_": "chatAdminRights",
                    "pFlags": {"post_messages": True, "delete_messages": True},
                },
                "rank": "Admin",
            },
        )
        assert promoted["_"] == "updates"

        admins = _invoke(
            client,
            owner_token,
            "channels.getParticipants",
            {
                "channel": channel,
                "filter": {"_": "channelParticipantsAdmins"},
                "offset": 0,
                "limit": 100,
                "hash": "0",
            },
        )
        admin_ids = {item["user_id"] for item in admins["participants"]}
        assert owner["id"] in admin_ids
        assert admin["id"] in admin_ids
        assert member["id"] not in admin_ids

        posted = _invoke(
            client,
            admin_token,
            "messages.sendMessage",
            {
                "peer": {"_": "inputPeerChannel", "channel_id": channel_id, "access_hash": "0"},
                "message": "admin post",
                "random_id": "admin-post",
            },
        )
        assert posted["updates"][0]["message"]["message"] == "admin post"

        denied = _request(
            client,
            member_token,
            "messages.sendMessage",
            {
                "peer": {"_": "inputPeerChannel", "channel_id": channel_id, "access_hash": "0"},
                "message": "subscriber post",
                "random_id": "member-post",
            },
        )
        assert denied.status_code == 403

        kicked = _invoke(
            client,
            admin_token,
            "channels.editBanned",
            {
                "channel": channel,
                "participant": _input_user(member),
                "banned_rights": {
                    "_": "chatBannedRights",
                    "until_date": 0,
                    "pFlags": {"view_messages": True},
                },
            },
        )
        assert kicked["_"] == "updates"

        denied_after_kick = _request(
            client,
            member_token,
            "channels.getParticipants",
            {"channel": channel, "offset": 0, "limit": 100, "hash": "0"},
        )
        assert denied_after_kick.status_code == 403
