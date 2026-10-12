from __future__ import annotations

import json
from typing import Any

from app.config import get_settings


class AzureDocumentQueue:
    """Durable Azure Storage Queue used to hand document work to a worker process."""

    def __init__(self) -> None:
        from azure.identity.aio import DefaultAzureCredential
        from azure.storage.queue.aio import QueueServiceClient

        settings = get_settings()
        if not settings.azure_storage_queue_account_url:
            raise RuntimeError("AZURE_STORAGE_QUEUE_ACCOUNT_URL is required for Azure Queue Storage")
        self.credential = DefaultAzureCredential()
        self.service = QueueServiceClient(
            account_url=settings.azure_storage_queue_account_url,
            credential=self.credential,
        )
        self.queue = self.service.get_queue_client(settings.azure_storage_queue_name)
        self.visibility_seconds = settings.queue_message_visibility_seconds

    async def enqueue(self, document_id: str) -> None:
        await self.queue.send_message(json.dumps({"document_id": document_id}))

    async def receive(self) -> Any | None:
        return await self.queue.receive_message(
            visibility_timeout=self.visibility_seconds,
            timeout=10,
        )

    async def acknowledge(self, message: Any) -> None:
        await self.queue.delete_message(message.id, message.pop_receipt)

    async def close(self) -> None:
        await self.service.close()
        await self.credential.close()


_document_queue: AzureDocumentQueue | None = None


def get_document_queue() -> AzureDocumentQueue:
    global _document_queue
    if _document_queue is None:
        _document_queue = AzureDocumentQueue()
    return _document_queue


async def close_document_queue() -> None:
    global _document_queue
    if _document_queue is not None:
        await _document_queue.close()
        _document_queue = None
