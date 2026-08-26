"""Bounded-memory physical Blob integrity for M10 historical/derived inputs."""
from __future__ import annotations
import asyncio
from typing import Literal
from soloring.assets.blob_store import BlobStore

async def blob_integrity_status(store: BlobStore, blob_hash: str) -> Literal["valid", "missing", "corrupt"]:
    if not store.validate_hash(blob_hash):
        return "corrupt"
    path = store.path_for_hash(blob_hash)
    actual = await asyncio.to_thread(store._hash_file, path)
    if actual == blob_hash:
        return "valid"
    if actual is not None:
        return "corrupt"
    return "corrupt" if await asyncio.to_thread(path.exists) else "missing"
