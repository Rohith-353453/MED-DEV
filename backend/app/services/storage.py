from __future__ import annotations

import asyncio
from pathlib import Path

from app.config import get_settings


class LocalStorage:
    def __init__(self) -> None:
        self.root = Path(get_settings().upload_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    async def put(self, key: str, content: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, content)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            await asyncio.to_thread(path.unlink)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("Invalid storage key")
        return path


class AzureBlobStorage:
    def __init__(self) -> None:
        from azure.identity.aio import DefaultAzureCredential
        from azure.storage.blob.aio import BlobServiceClient

        settings = get_settings()
        if not settings.azure_storage_account_url:
            raise RuntimeError("AZURE_STORAGE_ACCOUNT_URL is required for Azure Blob Storage")
        self.container_name = settings.azure_storage_container
        self.credential = DefaultAzureCredential()
        self.service = BlobServiceClient(settings.azure_storage_account_url, credential=self.credential)

    async def put(self, key: str, content: bytes, content_type: str) -> None:
        from azure.storage.blob import ContentSettings

        container = self.service.get_container_client(self.container_name)
        blob = container.get_blob_client(key)
        await blob.upload_blob(
            content,
            overwrite=False,
            content_settings=ContentSettings(content_type=content_type, cache_control="private, no-store"),
        )

    async def get(self, key: str) -> bytes:
        blob = self.service.get_blob_client(self.container_name, key)
        downloader = await blob.download_blob()
        return await downloader.readall()

    async def delete(self, key: str) -> None:
        blob = self.service.get_blob_client(self.container_name, key)
        await blob.delete_blob(delete_snapshots="include")

    async def close(self) -> None:
        await self.service.close()
        await self.credential.close()


_storage: LocalStorage | AzureBlobStorage | None = None


def get_storage() -> LocalStorage | AzureBlobStorage:
    global _storage
    if _storage is None:
        provider = get_settings().storage_provider
        _storage = AzureBlobStorage() if provider == "azure" else LocalStorage()
    return _storage


async def close_storage() -> None:
    if isinstance(_storage, AzureBlobStorage):
        await _storage.close()
