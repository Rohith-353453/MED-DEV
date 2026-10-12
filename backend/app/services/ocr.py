import asyncio
import hashlib
from dataclasses import dataclass

import httpx
from azure.identity.aio import DefaultAzureCredential

from app.config import get_settings


@dataclass
class OCRResult:
    raw_text: str
    page_count: int | None
    pages_processed: int
    confidence: float | None = None


class ProviderLimitError(RuntimeError):
    code = "OCR_LIMIT_EXCEEDED"


class MockOCRProvider:
    async def analyze(self, content: bytes, content_type: str) -> OCRResult:
        # Process only the explicitly marked synthetic fixture. Arbitrary user uploads
        # never receive invented OCR text or sample health facts.
        fixture_digest = "2005e9fe97934da2f904b17bed03471963e6ec0a91e0a9c2ed4d367b008f99e4"
        if hashlib.sha256(content).hexdigest() == fixture_digest:
            return OCRResult(
                raw_text=(
                    "CAREFOLIO DEMO FIXTURE V1\n"
                    "Synthetic lab report\n"
                    "Report date: 2026-01-15\n"
                    "Patient: Synthetic Demo\n"
                    "HGB: 12.8 g/dL; reference range 12.0-16.0; source flag N\n"
                    "Platelets: 420 x10^3/uL; reference range 150-400; source flag H\n"
                ),
                page_count=1,
                pages_processed=1,
                confidence=1.0,
            )
        return OCRResult(raw_text="", page_count=None, pages_processed=0, confidence=None)


class AzureDocumentIntelligenceProvider:
    async def analyze(self, content: bytes, content_type: str) -> OCRResult:
        settings = get_settings()
        if not settings.azure_document_intelligence_endpoint:
            raise RuntimeError("Azure Document Intelligence endpoint is not configured")
        if len(content) > settings.azure_document_intelligence_max_mb * 1024 * 1024:
            raise ProviderLimitError("Document exceeds the configured OCR service size limit")
        endpoint = settings.azure_document_intelligence_endpoint.rstrip("/")
        url = f"{endpoint}/documentintelligence/documentModels/prebuilt-layout:analyze"
        params = {"api-version": settings.azure_document_intelligence_api_version}
        if settings.max_document_pages > 0:
            params["pages"] = f"1-{settings.max_document_pages}"
        headers = {"Content-Type": content_type}
        credential = None
        if settings.azure_document_intelligence_key:
            headers["Ocp-Apim-Subscription-Key"] = settings.azure_document_intelligence_key
        else:
            credential = DefaultAzureCredential()
            token = await credential.get_token("https://cognitiveservices.azure.com/.default")
            headers["Authorization"] = f"Bearer {token.token}"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=90)) as client:
                response = await client.post(url, params=params, headers=headers, content=content)
                response.raise_for_status()
                operation_url = response.headers.get("operation-location")
                if not operation_url:
                    raise RuntimeError("Document Intelligence did not return an operation location")
                for _ in range(45):
                    result_response = await client.get(operation_url, headers=headers)
                    result_response.raise_for_status()
                    result = result_response.json()
                    state = result.get("status")
                    if state == "succeeded":
                        analysis = result.get("analyzeResult", {})
                        pages = analysis.get("pages", [])
                        return OCRResult(
                            raw_text=analysis.get("content", ""),
                            page_count=len(pages),
                            pages_processed=len(pages),
                            confidence=_mean_word_confidence(pages),
                        )
                    if state in {"failed", "canceled"}:
                        raise RuntimeError("Document Intelligence analysis failed")
                    await asyncio.sleep(1)
                raise TimeoutError("Document Intelligence analysis timed out")
        finally:
            if credential:
                await credential.close()


def _mean_word_confidence(pages: list[dict]) -> float | None:
    scores = [
        float(word["confidence"])
        for page in pages
        for word in page.get("words", [])
        if isinstance(word.get("confidence"), (float, int))
    ]
    return sum(scores) / len(scores) if scores else None


def get_ocr_provider() -> MockOCRProvider | AzureDocumentIntelligenceProvider:
    if get_settings().ocr_provider == "azure":
        return AzureDocumentIntelligenceProvider()
    return MockOCRProvider()
