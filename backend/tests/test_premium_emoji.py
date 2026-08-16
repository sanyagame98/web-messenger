from __future__ import annotations

import os
import zipfile
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./data/test_premium_emoji.db"
os.environ["SECRET_KEY"] = "roof-premium-emoji-test-key"

TEST_DB = Path(__file__).resolve().parents[1] / "data" / "test_premium_emoji.db"
TEST_DB.unlink(missing_ok=True)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.routers import premium_emoji  # noqa: E402


def _register(client: TestClient) -> str:
    response = client.post(
        "/api/auth/register",
        json={"email": "premium.emoji@example.com", "password": "roofpass123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_premium_emoji_zip_is_indexed_and_served(tmp_path: Path) -> None:
    packs_dir = tmp_path / "premium-emoji-packs"
    packs_dir.mkdir()
    archive_path = packs_dir / "My Animated Pack.zip"
    fake_tgs = b"\x1f\x8b\x08\x00roof-test-tgs"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("emoji/001.tgs", fake_tgs)
        archive.writestr("emoji/ignore.txt", b"not an emoji")

    old_dir = premium_emoji.PACKS_DIR
    premium_emoji.PACKS_DIR = packs_dir
    try:
        with TestClient(app) as client:
            token = _register(client)
            response = client.get(
                "/api/premium-emoji/packs",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["total_packs"] == 1
            assert data["total_emojis"] == 1
            pack = data["packs"][0]
            assert pack["title"] == "My Animated Pack"
            assert pack["count"] == 1
            emoji = pack["emojis"][0]
            assert emoji["status_token"].startswith(f"roof-tgs:{pack['id']}:")

            asset = client.get(emoji["url"])
            assert asset.status_code == 200, asset.text
            assert asset.content == fake_tgs
            assert asset.headers["content-type"].startswith("application/octet-stream")
    finally:
        premium_emoji.PACKS_DIR = old_dir
