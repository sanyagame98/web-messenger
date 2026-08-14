from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from app.main import app

_BYTES_KEY = "__roof_bytes_base64"


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


def _upload(client: TestClient, token: str, file_id: str, data: bytes) -> dict:
    assert _invoke(
        client,
        token,
        "upload.saveFilePart",
        {
            "file_id": file_id,
            "file_part": 0,
            "file_total_parts": 1,
            "bytes": {_BYTES_KEY: base64.b64encode(data).decode("ascii")},
        },
    ) is True
    return {
        "_": "inputFile",
        "id": file_id,
        "parts": 1,
        "name": f"{file_id}.jpg",
        "md5_checksum": "",
    }


def _input_user(user: dict) -> dict:
    return {"_": "inputUser", "user_id": user["id"], "access_hash": "0"}


def test_roof_user_avatar_upload_visibility_and_delete() -> None:
    with TestClient(app) as client:
        owner_token, owner = _register(client, "avatar.owner@example.com")
        viewer_token, _viewer = _register(client, "avatar.viewer@example.com")
        raw = b"roof-avatar-jpeg-bytes"
        uploaded_file = _upload(client, owner_token, "avatar-user-1301", raw)

        uploaded = _invoke(
            client,
            owner_token,
            "photos.uploadProfilePhoto",
            {"file": uploaded_file},
        )
        photo = uploaded["photo"]
        assert photo["_"] == "photo"

        users = _invoke(
            client,
            viewer_token,
            "users.getUsers",
            {"id": [_input_user(owner)]},
        )
        target = next(user for user in users if user["id"] == owner["id"])
        assert target["photo"]["_"] == "userProfilePhoto"
        assert target["photo"]["photo_id"] == photo["id"]

        downloaded = _invoke(
            client,
            viewer_token,
            "upload.getFile",
            {
                "location": {
                    "_": "inputPhotoFileLocation",
                    "id": photo["id"],
                    "access_hash": "0",
                    "file_reference": photo["file_reference"],
                    "thumb_size": "x",
                },
                "offset": 0,
                "limit": 1024,
            },
        )
        assert base64.b64decode(downloaded["bytes"][_BYTES_KEY]) == raw

        photos = _invoke(
            client,
            viewer_token,
            "photos.getUserPhotos",
            {"user_id": _input_user(owner), "offset": 0, "max_id": 0, "limit": 20},
        )
        assert photos["photos"][0]["id"] == photo["id"]

        deleted = _invoke(
            client,
            owner_token,
            "photos.deletePhotos",
            {"id": [{"_": "inputPhoto", "id": photo["id"], "access_hash": "0"}]},
        )
        assert deleted == [photo["id"]]

        users_after = _invoke(
            client,
            viewer_token,
            "users.getUsers",
            {"id": [_input_user(owner)]},
        )
        target_after = next(user for user in users_after if user["id"] == owner["id"])
        assert target_after["photo"]["_"] == "userProfilePhotoEmpty"


def test_roof_group_and_channel_photos_follow_admin_permissions() -> None:
    with TestClient(app) as client:
        owner_token, _owner = _register(client, "avatar.chat.owner@example.com")
        member_token, member = _register(client, "avatar.chat.member@example.com")

        group = _invoke(
            client,
            owner_token,
            "messages.createChat",
            {"title": "Roof Avatar Group", "users": [_input_user(member)]},
        )
        group_id = group["chats"][0]["id"]

        member_file = _upload(client, member_token, "avatar-denied-1302", b"denied")
        denied = _request(
            client,
            member_token,
            "messages.editChatPhoto",
            {
                "chat_id": group_id,
                "photo": {"_": "inputChatUploadedPhoto", "file": member_file},
            },
        )
        assert denied.status_code == 403

        group_file = _upload(client, owner_token, "avatar-group-1303", b"group-avatar")
        group_updated = _invoke(
            client,
            owner_token,
            "messages.editChatPhoto",
            {
                "chat_id": group_id,
                "photo": {"_": "inputChatUploadedPhoto", "file": group_file},
            },
        )
        assert group_updated["chats"][0]["photo"]["_"] == "chatPhoto"

        channel_created = _invoke(
            client,
            owner_token,
            "channels.createChannel",
            {"title": "Roof Avatar Channel", "about": "", "broadcast": True},
        )
        channel_id = channel_created["chats"][0]["id"]
        channel = {"_": "inputChannel", "channel_id": channel_id, "access_hash": "0"}
        _invoke(
            client,
            owner_token,
            "channels.inviteToChannel",
            {"channel": channel, "users": [_input_user(member)]},
        )

        channel_file = _upload(client, owner_token, "avatar-channel-1304", b"channel-avatar")
        channel_updated = _invoke(
            client,
            owner_token,
            "channels.editPhoto",
            {
                "channel": channel,
                "photo": {"_": "inputChatUploadedPhoto", "file": channel_file},
            },
        )
        assert channel_updated["chats"][0]["photo"]["_"] == "chatPhoto"

        dialogs = _invoke(client, member_token, "messages.getDialogs", {"limit": 100})
        by_id = {chat["id"]: chat for chat in dialogs["chats"]}
        assert by_id[group_id]["photo"]["_"] == "chatPhoto"
        assert by_id[channel_id]["photo"]["_"] == "chatPhoto"
