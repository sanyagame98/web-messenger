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


def test_saved_messages_send_reply_search_pin_and_forward() -> None:
    with TestClient(app) as client:
        token, me = _register(client, "saved.messages@example.com")
        other_token, other = _register(client, "saved.other@example.com")
        self_peer = {"_": "inputPeerSelf"}
        other_peer = {
            "_": "inputPeerUser",
            "user_id": other["id"],
            "access_hash": "0",
        }

        first = _invoke(
            client,
            token,
            "messages.sendMessage",
            {"peer": self_peer, "message": "Roof saved note", "random_id": "201"},
        )
        first_message = first["updates"][0]["message"]
        first_id = first_message["id"]
        assert first_message["peer_id"]["user_id"] == me["id"]

        reply = _invoke(
            client,
            token,
            "messages.sendMessage",
            {
                "peer": self_peer,
                "message": "Roof saved reply",
                "random_id": "202",
                "reply_to": {
                    "_": "inputReplyToMessage",
                    "reply_to_msg_id": first_id,
                },
            },
        )
        assert reply["updates"][0]["message"]["reply_to"]["reply_to_msg_id"] == first_id

        dialogs = _invoke(client, token, "messages.getDialogs", {"limit": 20})
        saved_dialog = next(
            dialog
            for dialog in dialogs["dialogs"]
            if dialog["peer"].get("user_id") == me["id"]
        )
        assert saved_dialog["top_message"] == reply["updates"][0]["message"]["id"]

        search = _invoke(
            client,
            token,
            "messages.search",
            {"peer": self_peer, "q": "saved note", "limit": 20},
        )
        assert search["messages"][0]["id"] == first_id

        _invoke(
            client,
            token,
            "messages.updatePinnedMessage",
            {"peer": self_peer, "id": first_id},
        )
        pins = _invoke(
            client,
            token,
            "messages.getPinnedHistory",
            {"peer": self_peer, "limit": 20},
        )
        assert pins["messages"][0]["pFlags"]["pinned"] is True

        direct = _invoke(
            client,
            other_token,
            "messages.sendMessage",
            {
                "peer": {
                    "_": "inputPeerUser",
                    "user_id": me["id"],
                    "access_hash": "0",
                },
                "message": "forward this to saved",
                "random_id": "203",
            },
        )
        source_id = direct["updates"][0]["message"]["id"]

        forwarded = _invoke(
            client,
            token,
            "messages.forwardMessages",
            {
                "from_peer": other_peer,
                "id": [source_id],
                "random_id": ["204"],
                "to_peer": self_peer,
            },
        )
        forwarded_message = forwarded["updates"][0]["message"]
        assert forwarded_message["message"] == "forward this to saved"
        assert forwarded_message["fwd_from"]["from_id"]["user_id"] == other["id"]

        history = _invoke(
            client,
            token,
            "messages.getHistory",
            {"peer": self_peer, "limit": 50},
        )
        assert any(
            message.get("fwd_from", {}).get("from_id", {}).get("user_id") == other["id"]
            for message in history["messages"]
        )
