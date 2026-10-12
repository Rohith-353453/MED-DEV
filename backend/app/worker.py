from __future__ import annotations

import asyncio
import json
import logging

from app.config import get_settings
from app.db import engine
from app.services.pipeline import process_document
from app.services.queue import close_document_queue, get_document_queue
from app.services.storage import close_storage
from app.telemetry import configure_telemetry

logger = logging.getLogger("carefolio.worker")


async def run() -> None:
    settings = get_settings()
    configure_telemetry()
    settings.validate_deployment_security()
    if settings.queue_provider != "azure":
        raise RuntimeError("The document worker requires QUEUE_PROVIDER=azure")

    queue = get_document_queue()
    logger.info("Document queue worker started")
    try:
        while True:
            try:
                message = await queue.receive()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Could not receive a queue message: error_type=%s", type(exc).__name__)
                await asyncio.sleep(5)
                continue

            if message is None:
                await asyncio.sleep(2)
                continue

            try:
                payload = json.loads(message.content)
                document_id = payload.get("document_id") if isinstance(payload, dict) else None
                if not isinstance(document_id, str) or not document_id:
                    logger.warning("Discarding malformed document queue message")
                    await queue.acknowledge(message)
                    continue

                await process_document(document_id)
                await queue.acknowledge(message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Leave the message unacknowledged. Azure Queue Storage makes it visible
                # again after the configured visibility timeout for a later retry.
                logger.error("Document queue work failed: error_type=%s", type(exc).__name__)
                await asyncio.sleep(2)
    finally:
        await close_document_queue()
        await close_storage()
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    asyncio.run(run())
