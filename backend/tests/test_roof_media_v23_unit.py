from app.routers.roof_tweb_v23 import _enable_video_streaming


def test_video_media_gets_streaming_flag() -> None:
    message = {
        "media": {
            "_": "messageMediaDocument",
            "document": {
                "attributes": [
                    {
                        "_": "documentAttributeVideo",
                        "duration": 5,
                        "w": 1280,
                        "h": 720,
                        "pFlags": {},
                    }
                ]
            },
        }
    }
    _enable_video_streaming(message)
    flags = message["media"]["document"]["attributes"][0]["pFlags"]
    assert flags["supports_streaming"] is True
