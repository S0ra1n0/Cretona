"""Three generation modes: text, image, text+image (S-08).

Contract: docs/API_CONTRACT.md Part II §5.

The rule this file exists to protect: a provider that cannot use an image
**refuses** the request. It never accepts one and returns a video generated
from the prompt alone, because the user has no way to tell the difference and
would reasonably believe their photo was used.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.project_service import generation_mode
from tests.conftest import USER_A

HEADERS = {"X-Debug-User-Id": USER_A}
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00"


def funded(client: TestClient, credits: int = 20) -> None:
    client.app.state.database.upsert_user(USER_A, email="a@example.com", username="a")
    client.app.state.credit_service.grant(USER_A, credits, reason="purchase")


def upload(client: TestClient) -> str:
    response = client.post(
        "/api/v1/uploads",
        headers=HEADERS,
        files={"file": ("reference.jpg", io.BytesIO(JPEG), "image/jpeg")},
    )
    assert response.status_code == 201
    return response.json()["storagePath"]


def create(client: TestClient, **body):
    return client.post("/api/v1/projects", headers=HEADERS, json=body)


# --- deriving the mode -------------------------------------------------------


@pytest.mark.parametrize(
    ("prompt", "image", "expected"),
    [
        ("a dragon", None, "text"),
        (None, "user/x.jpg", "image"),
        ("a dragon", "user/x.jpg", "text_image"),
        ("", "user/x.jpg", "image"),  # blank prompt is no prompt
        ("   ", "user/x.jpg", "image"),
        (None, None, "text"),  # rejected earlier by validation
    ],
)
def test_the_mode_follows_the_inputs(prompt, image, expected) -> None:
    assert generation_mode(prompt, image) == expected


# --- text mode ---------------------------------------------------------------


def test_a_prompt_alone_is_text_mode(client: TestClient) -> None:
    funded(client)

    body = create(client, prompt="a paper dragon", provider="fake").json()

    assert body["mode"] == "text"
    assert body["prompt"] == "a paper dragon"


# --- image and text+image ----------------------------------------------------


def test_an_image_alone_is_image_mode(client: TestClient) -> None:
    funded(client)
    path = upload(client)

    body = create(client, imagePath=path, provider="local").json()

    assert body["mode"] == "image"
    assert body["prompt"] is None
    assert body["imageUrl"] is not None


def test_an_image_alone_still_gets_a_title(client: TestClient) -> None:
    """There is no prompt to derive one from, and a blank title reads as a bug."""
    funded(client)
    path = upload(client)

    body = create(client, imagePath=path, provider="local").json()

    assert body["title"]


def test_both_inputs_are_text_image_mode(client: TestClient) -> None:
    funded(client)
    path = upload(client)

    body = create(client, prompt="make it flow", imagePath=path, provider="local").json()

    assert body["mode"] == "text_image"


# --- the refusal that matters ------------------------------------------------


def test_a_provider_that_cannot_use_an_image_refuses_it(client: TestClient) -> None:
    """The whole point of S-08.

    `fake` returns a bundled clip. Accepting an image here and handing back
    that clip would look like success to the user and to the app.
    """
    funded(client)
    path = upload(client)

    response = create(client, imagePath=path, provider="fake")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "PROVIDER_ERROR"


def test_the_refusal_also_covers_text_plus_image(client: TestClient) -> None:
    """Having a prompt does not make ignoring the image acceptable."""
    funded(client)
    path = upload(client)

    response = create(client, prompt="a dragon", imagePath=path, provider="fake")

    assert response.status_code == 502


def test_the_refusal_tells_the_user_what_to_do(client: TestClient) -> None:
    funded(client)
    path = upload(client)

    message = create(client, imagePath=path, provider="fake").json()["error"]["message"]

    assert "not available" in message.lower()
    assert "remove the image" in message.lower()


def test_a_refused_request_costs_nothing_and_creates_nothing(
    client: TestClient,
) -> None:
    """The check runs before the charge and before the row."""
    funded(client, 10)
    path = upload(client)

    create(client, imagePath=path, provider="fake")

    assert client.app.state.credit_service.balance(USER_A) == 10
    assert client.get("/api/v1/projects", headers=HEADERS).json()["items"] == []


def test_the_same_prompt_still_works_without_the_image(client: TestClient) -> None:
    """The message says to remove the image, so that has to actually work."""
    funded(client)
    path = upload(client)
    assert create(client, prompt="a dragon", imagePath=path, provider="fake").status_code == 502

    assert create(client, prompt="a dragon", provider="fake").status_code == 201


# --- validation --------------------------------------------------------------


def test_neither_input_is_rejected(client: TestClient) -> None:
    funded(client)

    response = create(client, provider="fake")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a_blank_prompt_with_no_image_is_rejected(client: TestClient) -> None:
    funded(client)

    assert create(client, prompt="   ", provider="fake").status_code == 400


# --- ordering ----------------------------------------------------------------


def test_ownership_is_checked_before_provider_capability(client: TestClient) -> None:
    """Otherwise the error tells an attacker which check they tripped.

    A 502 for someone else's path and a 403 for their own would let a caller
    probe whether a storage path exists by reading the status code.
    """
    funded(client)

    response = create(client, imagePath="other-user/2026-08-15/stolen.png", provider="fake")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_the_mode_survives_a_reload(client: TestClient) -> None:
    """Recomputed from the stored inputs, so it cannot drift from them."""
    funded(client)
    path = upload(client)
    created = create(client, prompt="make it flow", imagePath=path, provider="local").json()

    fetched = client.get(f"/api/v1/projects/{created['id']}", headers=HEADERS).json()

    assert fetched["mode"] == "text_image"
