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


def _bytes(value: bytes) -> dict[str, str]:
    return {_BYTES_KEY: base64.b64encode(value).decode("ascii")}


def _input_user(user: dict) -> dict:
    return {"_": "inputPeerUser", "user_id": user["id"], "access_hash": "0"}


def _input_file(file_id: str, parts: int, name: str) -> dict:
    return {
        "_": "inputFile",
        "id": file_id,
        "parts": parts,
        "name": name,
        "md5_checksum": "",
    }


def test_roof_photo_upload_send_history_and_download() -> None:
    with TestClient(app) as client:
        sender_token, sender = _register(client, "media.sender@example.com")
        receiver_token, receiver = _register(client, "media.receiver@example.com")
        raw = b"roof-photo-bytes-123"

        assert _invoke(
            client,
            sender_token,
            "upload.saveFilePart",
            {
                "file_id": "photo-501",
                "file_part": 0,
                "file_total_parts": 1,
                "bytes": _bytes(raw),
            },
        ) is True

        sent = _invoke(
            client,
            sender_token,
            "messages.sendMedia",
            {
                "peer": _input_user(receiver),
                "media": {
                    "_": "inputMediaUploadedPhoto",
                    "file": _input_file("photo-501", 1, "roof.png"),
                    "pFlags": {},
                },
                "message": "Roof photo",
                "random_id": "photo-random-id",
            },
        )
        message = sent["updates"][0]["message"]
        assert message["message"] == "Roof photo"
        assert message["media"]["_"] == "messageMediaPhoto"
        photo = message["media"]["photo"]
        photo_id = photo["id"]

        history = _invoke(
            client,
            receiver_token,
            "messages.getHistory",
            {"peer": _input_user(sender), "offset_id": 0, "limit": 50},
        )
        matching = [item for item in history["messages"] if item["id"] == message["id"]]
        assert matching[0]["media"]["_"] == "messageMediaPhoto"

        downloaded = _invoke(
            client,
            receiver_token,
            "upload.getFile",
            {
                "location": {
                    "_": "inputPhotoFileLocation",
                    "id": photo_id,
                    "access_hash": "0",
                    "file_reference": photo["file_reference"],
                    "thumb_size": "x",
                },
                "offset": 0,
                "limit": 1024,
            },
        )
        assert base64.b64decode(downloaded["bytes"][_BYTES_KEY]) == raw


def test_roof_document_parts_and_channel_media_permissions() -> None:
    with TestClient(app) as client:
        owner_token, _owner = _register(client, "media.channel.owner@example.com")
        member_token, member = _register(client, "media.channel.member@example.com")

        created = _invoke(
            client,
            owner_token,
            "channels.createChannel",
            {"title": "Roof Media", "about": "", "broadcast": True},
        )
        channel_id = created["chats"][0]["id"]
        channel = {"_": "inputChannel", "channel_id": channel_id, "access_hash": "0"}
        _invoke(
            client,
            owner_token,
            "channels.inviteToChannel",
            {
                "channel": channel,
                "users": [
                    {"_": "inputUser", "user_id": member["id"], "access_hash": "0"}
                ],
            },
        )

        first = b"Roof document part A - "
        second = b"part B"
        for index, chunk in enumerate((first, second)):
            assert _invoke(
                client,
                owner_token,
                "upload.saveBigFilePart",
                {
                    "file_id": "doc-701",
                    "file_part": index,
                    "file_total_parts": 2,
                    "bytes": _bytes(chunk),
                },
            ) is True

        sent = _invoke(
            client,
            owner_token,
            "messages.sendMedia",
            {
                "peer": {
                    "_": "inputPeerChannel",
                    "channel_id": channel_id,
                    "access_hash": "0",
                },
                "media": {
                    "_": "inputMediaUploadedDocument",
                    "file": _input_file("doc-701", 2, "notes.txt"),
                    "mime_type": "text/plain",
                    "attributes": [
                        {"_": "documentAttributeFilename", "file_name": "notes.txt"}
                    ],
                    "pFlags": {},
                },
                "message": "Roof document",
            },
        )
        document = sent["updates"][0]["message"]["media"]["document"]
        assert document["mime_type"] == "text/plain"
        assert document["size"] == len(first + second)

        denied_bytes = b"subscriber cannot post"
        _invoke(
            client,
            member_token,
            "upload.saveFilePart",
            {
                "file_id": "denied-801",
                "file_part": 0,
                "file_total_parts": 1,
                "bytes": _bytes(denied_bytes),
            },
        )
        denied = _request(
            client,
            member_token,
            "messages.sendMedia",
            {
                "peer": {
                    "_": "inputPeerChannel",
                    "channel_id": channel_id,
                    "access_hash": "0",
                },
                "media": {
                    "_": "inputMediaUploadedDocument",
                    "file": _input_file("denied-801", 1, "denied.txt"),
                    "mime_type": "text/plain",
                    "attributes": [],
                },
                "message": "Nope",
            },
        )
        assert denied.status_code == 403
