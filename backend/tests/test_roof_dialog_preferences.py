from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/test_roof_tweb.db")
os.environ.setdefault("SECRET_KEY", "roof-test-secret-key")

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
):
    response = client.post(
        "/api/roof/invoke",
        headers={"Authorization": f"Bearer {token}"},
        json={"method": method, "params": params or {}},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_pin_and_mute_are_per_user() -> None:
    with TestClient(app) as client:
        alice_token, alice = _register(client, "prefs.alice@example.com")
        bob_token, bob = _register(client, "prefs.bob@example.com")
        bob_peer = {
            "_": "inputPeerUser",
            "user_id": bob["id"],
            "access_hash": "0",
        }
        alice_peer = {
            "_": "inputPeerUser",
            "user_id": alice["id"],
            "access_hash": "0",
        }

        _invoke(
            client,
            alice_token,
            "messages.sendMessage",
            {"peer": bob_peer, "message": "prefs chat", "random_id": "301"},
        )

        assert _invoke(
            client,
            alice_token,
            "messages.toggleDialogPin",
            {"peer": bob_peer, "pinned": True},
        ) is True

        pinned = _invoke(
            client,
            alice_token,
            "messages.getPinnedDialogs",
            {"folder_id": 0},
        )
        assert len(pinned["dialogs"]) == 1
        assert pinned["dialogs"][0]["pFlags"]["pinned"] is True

        bob_pinned = _invoke(
            client,
            bob_token,
            "messages.getPinnedDialogs",
            {"folder_id": 0},
        )
        assert bob_pinned["dialogs"] == []

        mute_until = 2_000_000_000
        assert _invoke(
            client,
            alice_token,
            "account.updateNotifySettings",
            {
                "peer": {"_": "inputNotifyPeer", "peer": bob_peer},
                "settings": {
                    "_": "inputPeerNotifySettings",
                    "mute_until": mute_until,
                    "pFlags": {"show_previews": True, "silent": True},
                },
            },
        ) is True

        notify = _invoke(
            client,
            alice_token,
            "account.getNotifySettings",
            {"peer": {"_": "inputNotifyPeer", "peer": bob_peer}},
        )
        assert notify["mute_until"] == mute_until
        assert notify["pFlags"]["silent"] is True

        dialogs = _invoke(client, alice_token, "messages.getDialogs", {"limit": 20})
        dialog = next(
            item
            for item in dialogs["dialogs"]
            if item["peer"].get("user_id") == bob["id"]
        )
        assert dialog["notify_settings"]["mute_until"] == mute_until

        bob_notify = _invoke(
            client,
            bob_token,
            "account.getNotifySettings",
            {"peer": {"_": "inputNotifyPeer", "peer": alice_peer}},
        )
        assert bob_notify["mute_until"] == 0
