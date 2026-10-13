from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.middleware import wrap_with_cors
from app.routers import documents
from app.schemas import SummaryGenerateRequest

FRONTEND_ORIGIN = "https://white-island-0d7509300.1.azurestaticapps.net"


@pytest.mark.anyio
async def test_preflight_allows_firebase_post_headers() -> None:
    app = wrap_with_cors(FastAPI(), [FRONTEND_ORIGIN])
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/documents/test-document/summaries",
            headers={
                "Origin": FRONTEND_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN
    assert "POST" in response.headers["access-control-allow-methods"]
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed_headers
    assert "content-type" in allowed_headers


@pytest.mark.anyio
async def test_unhandled_error_keeps_cors_headers() -> None:
    api = FastAPI()

    @api.get("/unexpected-error")
    async def unexpected_error() -> None:
        raise RuntimeError("provider failure")

    app = wrap_with_cors(api, [FRONTEND_ORIGIN])
    transport = ASGITransport(app=app, raise_app_exceptions=False)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/unexpected-error",
            headers={"Origin": FRONTEND_ORIGIN},
        )

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN


@pytest.mark.anyio
async def test_summary_provider_failure_returns_useful_gateway_error(monkeypatch) -> None:
    document = SimpleNamespace(
        id="test-document",
        extracted_data={},
        page_count=None,
        pages_processed=0,
    )
    profile = SimpleNamespace(id="test-owner", preferred_language="en")

    async def get_document(*_args):
        return document

    class FailingProvider:
        async def summarize(self, _extracted, _language):
            raise RuntimeError("provider failure")

        async def close(self):
            return None

    monkeypatch.setattr(documents, "get_owned_document", get_document)
    monkeypatch.setattr(documents, "get_ai_provider", FailingProvider)

    with pytest.raises(HTTPException) as error:
        await documents.generate_summary(
            "test-document",
            SummaryGenerateRequest(language="hi"),
            profile,
            object(),
        )

    assert error.value.status_code == 502
    assert error.value.detail == (
        "The summary service could not complete this request. Please try again later."
    )
