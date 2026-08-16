import io

from fastapi.testclient import TestClient


def test_sign_upload_endpoint(client: TestClient, user_headers: dict[str, str]):
    response = client.post(
        "/api/v1/uploads/sign",
        headers=user_headers,
        json={"contentType": "image/png", "sizeBytes": 1024 * 100},
    )
    assert response.status_code == 200
    data = response.json()
    assert "uploadUrl" in data
    assert "storagePath" in data
    assert data["storagePath"].endswith(".png")


def test_direct_multipart_upload_endpoint(client: TestClient, user_headers: dict[str, str]):
    fake_png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    )
    files = {"file": ("test_frame.png", io.BytesIO(fake_png_bytes), "image/png")}

    response = client.post("/api/v1/uploads", headers=user_headers, files=files)
    assert response.status_code == 201
    data = response.json()
    assert "storagePath" in data
    assert "imageUrl" in data
    assert data["imageUrl"] is not None


def test_direct_multipart_upload_rejects_invalid_type(
    client: TestClient, user_headers: dict[str, str]
):
    files = {"file": ("script.sh", io.BytesIO(b"echo 'hello'"), "text/plain")}

    response = client.post("/api/v1/uploads", headers=user_headers, files=files)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_project_with_image_path(client: TestClient, user_headers: dict[str, str]):
    # 1. Upload image
    fake_jpg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00"
    upload_res = client.post(
        "/api/v1/uploads",
        headers=user_headers,
        files={"file": ("reference.jpg", io.BytesIO(fake_jpg), "image/jpeg")},
    )
    assert upload_res.status_code == 201
    storage_path = upload_res.json()["storagePath"]

    # 2. Create project using the imagePath
    proj_res = client.post(
        "/api/v1/projects",
        headers=user_headers,
        json={
            "prompt": "Animate this painting into flowing water",
            "imagePath": storage_path,
            "provider": "fake",
        },
    )
    assert proj_res.status_code == 201
    proj_data = proj_res.json()
    assert proj_data["status"] == "pending"
    assert proj_data["imageUrl"] is not None
    assert storage_path in proj_data["imageUrl"]


def test_create_project_rejects_unowned_image_path(
    client: TestClient, user_headers: dict[str, str]
):
    proj_res = client.post(
        "/api/v1/projects",
        headers=user_headers,
        json={
            "prompt": "Steal another user's image",
            "imagePath": "other-user/2026-08-15/stolen.png",
            "provider": "fake",
        },
    )
    assert proj_res.status_code == 403
    assert proj_res.json()["error"]["code"] == "FORBIDDEN"
