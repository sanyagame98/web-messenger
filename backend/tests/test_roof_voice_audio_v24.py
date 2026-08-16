from __future__ import annotations

import base64
import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./data/test_roof_voice_audio_v24.db"
os.environ["SECRET_KEY"] = "roof-test-secret-key"

TEST_DB = Path(__file__).resolve().parents[1] / "data" / "test_roof_voice_audio_v24.db"
TEST_DB.unlink(missing_ok=True)

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

BYTES = "__roof_bytes_base64"


def reg(client: TestClient, email: str):
    data = client.post("/api/auth/register", json={"email": email, "password": "roofpass123"}).json()
    return data["access_token"], data["user"]


def invoke(client: TestClient, token: str, method: str, params: dict):
    response = client.post("/api/roof/invoke", headers={"Authorization": f"Bearer {token}"}, json={"method": method, "params": params})
    assert response.status_code == 200, response.text
    return response.json()


def upload(client: TestClient, token: str, file_id: str, raw: bytes):
    return invoke(client, token, "upload.saveFilePart", {"file_id": file_id, "file_part": 0, "file_total_parts": 1, "bytes": {BYTES: base64.b64encode(raw).decode()}})


def test_voice_waveform_and_audio_metadata_survive_history():
    with TestClient(app) as client:
        token, _me = reg(client, "voice.sender@example.com")
        _other_token, other = reg(client, "voice.receiver@example.com")
        peer = {"_": "inputPeerUser", "user_id": other["id"], "access_hash": "0"}

        upload(client, token, "voice-1", b"fake-opus-voice")
        sent = invoke(client, token, "messages.sendMedia", {
            "peer": peer,
            "media": {
                "_": "inputMediaUploadedDocument",
                "file": {"_": "inputFile", "id": "voice-1", "parts": 1, "name": "voice.webm", "md5_checksum": ""},
                "mime_type": "audio/webm",
                "attributes": [
                    {"_": "documentAttributeFilename", "file_name": "voice.webm"},
                    {"_": "documentAttributeAudio", "duration": 7, "waveform": [10, 40, 90, 35], "pFlags": {"voice": True}},
                ],
            },
            "message": "",
        })
        voice_id = sent["updates"][0]["message"]["id"]

        upload(client, token, "audio-1", b"fake-mp3")
        sent_audio = invoke(client, token, "messages.sendMedia", {
            "peer": peer,
            "media": {
                "_": "inputMediaUploadedDocument",
                "file": {"_": "inputFile", "id": "audio-1", "parts": 1, "name": "track.mp3", "md5_checksum": ""},
                "mime_type": "audio/mpeg",
                "attributes": [
                    {"_": "documentAttributeFilename", "file_name": "track.mp3"},
                    {"_": "documentAttributeAudio", "duration": 123, "title": "Roof Track", "performer": "Roof Artist", "pFlags": {}},
                ],
            },
            "message": "music",
        })
        audio_id = sent_audio["updates"][0]["message"]["id"]

        history = invoke(client, token, "messages.getHistory", {"peer": peer, "offset_id": 0, "limit": 50})
        by_id = {item["id"]: item for item in history["messages"]}

        voice_attrs = by_id[voice_id]["media"]["document"]["attributes"]
        voice = next(item for item in voice_attrs if item["_"] == "documentAttributeAudio")
        assert voice["pFlags"]["voice"] is True
        assert voice["duration"] == 7
        assert voice["waveform"] == [10, 40, 90, 35]

        audio_attrs = by_id[audio_id]["media"]["document"]["attributes"]
        audio = next(item for item in audio_attrs if item["_"] == "documentAttributeAudio")
        assert audio["duration"] == 123
        assert audio["title"] == "Roof Track"
        assert audio["performer"] == "Roof Artist"
