import time
from pathlib import Path

from app.core.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_clean_database_upload_background_history_and_download(tmp_path, commercial_files):
    data = tmp_path / "data"
    settings = Settings(data, f"sqlite:///{(data / 'database/test.db').as_posix()}")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/history").json()["total"] == 0
        assert (
            client.post("/api/tnved/runs", files={"file": ("broken.xlsx", b"not a zip")}).status_code == 422
        )
        response = client.post(
            "/api/merchandise/runs",
            files=[
                (
                    "files",
                    (
                        f.original_name,
                        Path(f.path).read_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ),
                )
                for f in commercial_files
            ],
        )
        assert response.status_code == 202
        identifier = response.json()["id"]
        for _ in range(150):
            job = client.get(f"/api/jobs/{identifier}").json()
            if job["status"] in ("completed", "failed"):
                break
            time.sleep(0.1)
        assert job["status"] == "completed", job
        assert job["progress"] == 100
        assert job["created_at"].endswith("+00:00")
        assert client.get("/api/history").json()["total"] == 1
        assert client.get(f"/api/merchandise/runs/{identifier}/articles").json()["total"] == 1
        assert client.get(f"/api/merchandise/runs/{identifier}/articles?q=NOTFOUND").json()["total"] == 0
        assert client.get(f"/api/merchandise/runs/{identifier}/export").content[:2] == b"PK"
        assert client.get(f"/api/tnved/runs/{identifier}").status_code == 404
    # Results survive process/app restart, and the same migration runs idempotently.
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/history").json()["items"][0]["id"] == identifier
        assert client.get(f"/api/merchandise/runs/{identifier}/articles/6A-TEST").json()["base"] == 1000
