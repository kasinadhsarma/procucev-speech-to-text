import os
os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["PRELOAD_MODEL"] = "0"

from fastapi.testclient import TestClient
from app.main import app


def test_crud():
    with TestClient(app) as c:
        r = c.post("/api/transcriptions", json={"title": "t", "text": "नमस्ते hello world"})
        assert r.status_code == 201
        tid = r.json()["id"]
        assert c.get(f"/api/transcriptions/{tid}").json()["text"].startswith("नमस्ते")
        assert any(x["id"] == tid for x in c.get("/api/transcriptions?q=hello").json())
        assert c.put(f"/api/transcriptions/{tid}", json={"text": "updated"}).json()["text"] == "updated"
        assert c.delete(f"/api/transcriptions/{tid}").status_code == 204
        assert c.get(f"/api/transcriptions/{tid}").status_code == 404
