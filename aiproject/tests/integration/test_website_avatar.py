from base64 import b64decode
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.modules.visitor import router as visitor_router
from tests.integration.test_ent_portal_routes import isolated_portal


def test_website_profile_and_avatar_belong_to_authenticated_account(isolated_portal, monkeypatch):
    app, engine = isolated_portal("trusted_jwt")
    monkeypatch.setattr(visitor_router, "_AUTH_CAPACITY", visitor_router.CsChatCapacity(4, 2, 10))
    base = "/api/v1/visitors"

    def avatar_file(color):
        with BytesIO() as output:
            Image.new("RGB", (420, 280), color).save(output, "PNG")
            return {"file": ("picture.png", output.getvalue(), "image/png")}

    def new_account(client, username):
        result = client.post(base + "/register", json={"username": username, "password": "Test!4567"})
        assert result.status_code == 201
        return {"Authorization": "Bearer " + result.json()["data"]["access_token"]}

    try:
        with TestClient(app) as client:
            assert client.get(base + "/profile").status_code == 401
            assert client.put(base + "/avatar", files=avatar_file("blue")).status_code == 401
            first = new_account(client, "13900009101")
            second = new_account(client, "13900009102")
            own = client.get(base + "/profile", headers=first)
            assert own.status_code == 200 and own.headers["cache-control"] == "no-store"
            profile = own.json()["data"]
            assert profile["username"] == profile["contact"] == "13900009101"
            assert profile["name"] == "" and profile["nickname"] is None
            assert profile["account_type"] == "visitor" and profile["avatar_url"] is None
            assert profile["version"] is None
            assert set(profile) == {"username", "name", "nickname", "contact", "account_type", "created_at", "avatar_url", "version"}

            uploaded = client.put(base + "/avatar", headers=first, files=avatar_file("blue"))
            assert uploaded.status_code == 200
            url = uploaded.json()["data"]["avatar_url"]
            assert url.startswith("data:image/webp;base64,")
            with Image.open(BytesIO(b64decode(url.split(",", 1)[1]))) as avatar:
                assert avatar.format == "WEBP" and avatar.size == (256, 256)
            assert client.get(base + "/profile", headers=first).json()["data"]["avatar_url"] == url
            assert client.get(base + "/profile", headers=second).json()["data"]["avatar_url"] is None

            fields = {"nickname": " 新昵称 ", "name": " 新姓名 ", "contact": " contact@example.test "}
            assert client.put(base + "/profile", json=fields).status_code == 401
            assert client.put(base + "/profile", headers=first, json={**fields, "username": "13900009102"}).status_code == 422
            saved = client.put(base + "/profile", headers=first, json=fields)
            assert saved.status_code == 200 and saved.headers["cache-control"] == "no-store"
            expected = {**profile, "nickname": "新昵称", "name": "新姓名", "contact": "contact@example.test", "avatar_url": url}
            assert saved.json()["data"] == expected
            assert client.get(base + "/profile", headers=first).json()["data"] == expected
            other = client.get(base + "/profile", headers=second).json()["data"]
            assert other["name"] == "" and other["contact"] == "13900009102" and other["nickname"] is None
            blank = client.put(base + "/profile", headers=first, json={**fields, "name": "   "})
            assert blank.status_code == 200 and blank.json()["data"]["name"] == ""

            bogus = {"file": ("forged.png", b"<svg></svg>", "image/png")}
            assert client.put(base + "/avatar", headers=first, files=bogus).status_code == 422
            oversize = {"file": ("oversize.png", b"x" * (2 * 1024 * 1024 + 1), "image/png")}
            assert client.put(base + "/avatar", headers=first, files=oversize).status_code == 413
            assert client.get(base + "/profile", headers=first).json()["data"]["avatar_url"] == url

            replaced = client.put(base + "/avatar", headers=first, files=avatar_file("green"))
            assert replaced.status_code == 200 and replaced.json()["data"]["avatar_url"] != url
            assert client.post(base + "/logout", headers=first).status_code == 200
            assert client.get(base + "/profile", headers=first).status_code == 401
            assert client.put(base + "/profile", headers=first, json=fields).status_code == 401
            logged_in = client.post(base + "/login", json={"username": "13900009101", "password": "Test!4567"})
            fresh = {"Authorization": "Bearer " + logged_in.json()["data"]["access_token"]}
            assert client.get(base + "/profile", headers=fresh).json()["data"]["avatar_url"] == replaced.json()["data"]["avatar_url"]
    finally:
        engine.dispose()
