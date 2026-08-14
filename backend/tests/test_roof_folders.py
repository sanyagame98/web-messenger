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


def _invoke(client: TestClient, token: str, method: str, params: dict | None = None):
    response = client.post(
        "/api/roof/invoke",
        headers={"Authorization": f"Bearer {token}"},
        json={"method": method, "params": params or {}},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_roof_archive_and_custom_chat_folders() -> None:
    with TestClient(app) as client:
        owner_token, owner = _register(client, "folders.owner@example.com")
        peer_token, peer = _register(client, "folders.peer@example.com")
        owner_peer = {
            "_": "inputPeerUser",
            "user_id": peer["id"],
            "access_hash": "0",
        }
        peer_owner = {
            "_": "inputPeerUser",
            "user_id": owner["id"],
            "access_hash": "0",
        }

        _invoke(
            client,
            owner_token,
            "messages.sendMessage",
            {"peer": owner_peer, "message": "archive me", "random_id": "folder-1"},
        )
        _invoke(client, peer_token, "messages.getHistory", {"peer": peer_owner, "limit": 10})

        moved = _invoke(
            client,
            owner_token,
            "folders.editPeerFolders",
            {
                "folder_peers": [
                    {"_": "inputFolderPeer", "peer": owner_peer, "folder_id": 1}
                ]
            },
        )
        assert moved["updates"][0]["_"] == "updateFolderPeers"

        archived = _invoke(
            client,
            owner_token,
            "messages.getDialogs",
            {"folder_id": 1, "limit": 100},
        )
        assert len(archived["dialogs"]) == 1
        assert archived["dialogs"][0]["folder_id"] == 1

        inbox = _invoke(
            client,
            owner_token,
            "messages.getDialogs",
            {"folder_id": 0, "limit": 100},
        )
        assert inbox["dialogs"] == []

        work_filter = {
            "_": "dialogFilter",
            "pFlags": {"contacts": True, "groups": True},
            "id": 2,
            "title": {"_": "textWithEntities", "text": "Work", "entities": []},
            "emoticon": "💼",
            "pinned_peers": [],
            "include_peers": [owner_peer],
            "exclude_peers": [],
        }
        assert _invoke(
            client,
            owner_token,
            "messages.updateDialogFilter",
            {"id": 2, "filter": work_filter},
        ) is True

        fun_filter = {
            "_": "dialogFilter",
            "pFlags": {"groups": True},
            "id": 3,
            "title": {"_": "textWithEntities", "text": "Fun", "entities": []},
            "pinned_peers": [],
            "include_peers": [],
            "exclude_peers": [],
        }
        assert _invoke(
            client,
            owner_token,
            "messages.updateDialogFilter",
            {"id": 3, "filter": fun_filter},
        ) is True
        assert _invoke(
            client,
            owner_token,
            "messages.updateDialogFiltersOrder",
            {"order": [3, 2]},
        ) is True

        filters = _invoke(client, owner_token, "messages.getDialogFilters")
        assert [item["id"] for item in filters["filters"]] == [3, 2]
        assert filters["filters"][1]["title"]["text"] == "Work"

        assert _invoke(
            client,
            owner_token,
            "messages.updateDialogFilter",
            {"id": 2},
        ) is True
        filters_after_delete = _invoke(client, owner_token, "messages.getDialogFilters")
        assert [item["id"] for item in filters_after_delete["filters"]] == [3]

        _invoke(
            client,
            owner_token,
            "folders.editPeerFolders",
            {
                "folder_peers": [
                    {"_": "inputFolderPeer", "peer": owner_peer, "folder_id": 0}
                ]
            },
        )
        restored = _invoke(
            client,
            owner_token,
            "messages.getDialogs",
            {"folder_id": 0, "limit": 100},
        )
        assert len(restored["dialogs"]) == 1
        assert restored["dialogs"][0]["folder_id"] == 0
