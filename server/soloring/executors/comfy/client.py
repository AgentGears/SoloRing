"""ComfyClient — the ComfyUI HTTP boundary (M5A-6; M5 plan §54, §2-§4).

HTTP only: no DB, no worker authority, no Generation lifecycle, no knowledge
that ``submission_possible`` exists. Usable in isolated tests with only a base
URL + injectable httpx transport + the wire normalizers.

Operation-semantic retry policy (§54):
  * reads (system_stats/queue/history/view) — bounded transient retry;
  * ``submit_prompt`` — EXACTLY ONE HTTP request attempt. Transport failure,
    timeout, malformed 200, or 5xx are classified AMBIGUOUS (possibly sent)
    unless the endpoint contract conclusively proves otherwise. The client
    never replays /prompt; callers must rediscover via the attempt marker.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import httpx

from soloring.executors.comfy import wire
from soloring.executors.comfy.models import (
    NormalizedComfyJob,
    NormalizedHistoryRecord,
    NormalizedUploadReference,
)


class ComfyAPIError(RuntimeError):
    """Conclusive non-transient Comfy API failure."""


class SubmissionAmbiguous(RuntimeError):
    """A /prompt outcome that may have reached Comfy (possibly sent).

    Conservative classification (M5A-6 §3, §11): timeout, disconnect,
    malformed success response, or 5xx. NEVER retried by this client; the
    caller must rediscover via the embedded attempt marker.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class PromptAccepted:
    prompt_id: str


@dataclass(frozen=True)
class PromptRejected:
    """Conclusive pre-submission rejection (contract-proven 4xx class)."""

    status_code: int
    detail: str


class ComfyClient:
    def __init__(
        self,
        base_url: str,
        client_id: str,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self.client_id = client_id
        # NO transport-level retry transport: /prompt must never be replayed
        # by a generic layer (M5A-6 §2).
        self._client = httpx.AsyncClient(transport=transport, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    # --- read plumbing: bounded transient retry --------------------------------

    async def _request_read(
        self, method: str, path: str, *, params: dict | None = None
    ) -> httpx.Response:
        try:
            return await self._client.request(method, self._base + path, params=params)
        except httpx.HTTPError:
            await asyncio.sleep(0.05)
            try:
                return await self._client.request(
                    method, self._base + path, params=params
                )
            except httpx.HTTPError as exc:
                raise ComfyAPIError(f"Comfy unreachable: {path}") from exc

    async def _json_read(self, method: str, path: str, what: str) -> dict:
        response = await self._request_read(method, path)
        if response.status_code >= 500:
            raise ComfyAPIError(f"Comfy server error on {what}: {response.status_code}")
        if response.status_code >= 400:
            raise ComfyAPIError(f"Comfy rejected {what}: {response.status_code}")
        try:
            parsed = response.json()
        except ValueError as exc:
            raise ComfyAPIError(f"Malformed Comfy response on {what}") from exc
        if not isinstance(parsed, dict):
            raise ComfyAPIError(f"Malformed Comfy response on {what}")
        return parsed

    # --- capability/readiness ---------------------------------------------------
    # NOTE (audit F13): there is deliberately NO readiness() shortcut here.
    # Readiness is a CAPABILITY conclusion (capabilities.evaluate_readiness
    # over an evidence-backed ComfyCapabilityReport), not "one endpoint
    # answered 200". M5B-1 builds the live probe that produces the report.
    # This module only exposes the raw read surface:

    async def system_stats(self) -> dict:
        return await self._json_read("GET", "/system_stats", "system_stats")

    # --- inputs -------------------------------------------------------------------

    async def upload_input(
        self, *, source_path: Path, filename: str, subfolder: str
    ) -> NormalizedUploadReference:
        """Stream the verified source file into Comfy input storage (M5 §26).

        The file is streamed in bounded chunks via multipart; Comfy's returned
        name is authoritative (auto-renaming honored by the normalizer).
        """
        import hashlib

        hasher = hashlib.sha256()

        class _StreamFile:
            def read(self, size=-1):  # httpx protocol
                chunk = fh.read(size if size and size > 0 else 1 << 16)
                hasher.update(chunk)
                return chunk

        fh = open(source_path, "rb")
        try:
            files = {"image": (filename, _StreamFile(), "application/octet-stream")}
            data = {"overwrite": "true", "subfolder": subfolder}
            try:
                response = await self._client.post(
                    self._base + "/upload/image", files=files, data=data
                )
            except httpx.HTTPError as exc:
                raise ComfyAPIError("input upload transport failure") from exc
        finally:
            fh.close()
        if response.status_code >= 400:
            raise ComfyAPIError(
                f"input upload rejected: {response.status_code}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise ComfyAPIError("malformed upload response") from exc
        ref = wire.normalize_upload_response(body)
        if ref.subfolder and ref.subfolder != subfolder:
            # namespace containment is validated by the materializer; the
            # client surfaces the raw mismatch for its error path.
            pass
        return ref

    # --- submission: ONE request attempt, conservative ambiguity -------------------

    async def submit_prompt(
        self, payload_document: dict
    ) -> PromptAccepted | PromptRejected:
        """POST /prompt exactly once. Never retried by any layer below the
        caller's explicit rediscovery policy.

        Classification:
          * 200 + valid prompt_id → PromptAccepted
          * 200 malformed / invalid id → SubmissionAmbiguous (may be accepted)
          * 5xx → SubmissionAmbiguous (enqueue-then-error is possible)
          * timeout / disconnect / any transport error → SubmissionAmbiguous
          * 400 with a parseable body whose nodes were NOT executed → the
            only contract-proven conclusive rejection class (Comfy validates
            the graph before queueing; a validation error means no enqueue).
        """
        try:
            response = await self._client.post(
                self._base + "/prompt", json=payload_document
            )
        except httpx.HTTPError as exc:
            raise SubmissionAmbiguous(
                f"/prompt transport failure (possibly sent): {exc}"
            ) from exc

        if response.status_code == 200:
            try:
                prompt_id = wire.normalize_submit_response(response.json())
            except Exception as exc:  # noqa: BLE001
                raise SubmissionAmbiguous(
                    f"/prompt returned malformed success (possibly sent): {exc}"
                ) from exc
            return PromptAccepted(prompt_id=prompt_id)

        if 500 <= response.status_code < 600:
            raise SubmissionAmbiguous(
                f"/prompt returned {response.status_code} (possibly sent)"
            )

        if response.status_code == 400:
            # Contract-proven conclusive rejection: Comfy validates and
            # reports graph errors WITHOUT queueing. A parseable validation
            # body is required to earn this classification; anything else
            # stays ambiguous.
            try:
                body = response.json()
            except ValueError as exc:
                raise SubmissionAmbiguous(
                    "/prompt 400 with unparseable body (possibly sent)"
                ) from exc
            if isinstance(body, dict) and (
                "node_errors" in body or "error" in body
            ):
                return PromptRejected(
                    status_code=400, detail=str(body)[:200]
                )
            raise SubmissionAmbiguous(
                "/prompt 400 without validation body (possibly sent)"
            )

        raise SubmissionAmbiguous(
            f"/prompt returned unexpected status {response.status_code} "
            "(possibly sent)"
        )

    # --- observation ------------------------------------------------------------------

    async def queue(self) -> tuple[NormalizedComfyJob, ...]:
        return wire.normalize_queue_response(
            await self._json_read("GET", "/queue", "queue")
        )

    async def history(self, prompt_id: str | None = None) -> dict[str, NormalizedHistoryRecord]:
        path = "/history" if prompt_id is None else f"/history/{prompt_id}"
        return wire.normalize_history_response(
            await self._json_read("GET", path, "history")
        )

    # --- retrieval/cancellation transport (integration deferred to M5A-8/9) -----------

    async def fetch_view(
        self, filename: str, subfolder: str, output_type: str = "output"
    ) -> bytes:
        response = await self._request_read(
            "GET", "/view",
            params={"filename": filename, "subfolder": subfolder,
                    "type": output_type},
        )
        if response.status_code != 200:
            raise ComfyAPIError(f"view failed for {filename!r}: {response.status_code}")
        return response.content

    async def stream_view(
        self, filename: str, subfolder: str, output_type: str = "output",
        chunk_size: int = 1 << 20,
    ):
        """Async byte iterator over /view — ONE request, bounded chunks.

        This is the real transport for M5A-9's sync chunk-provider protocol:
        outputs are never buffered whole in memory, whatever their size. The
        iteration is not retried here; the staging fetcher owns whole-transfer
        retry-from-zero semantics.
        """
        try:
            async with self._client.stream(
                "GET", self._base + "/view",
                params={"filename": filename, "subfolder": subfolder,
                        "type": output_type},
            ) as response:
                if response.status_code != 200:
                    raise ComfyAPIError(
                        f"view failed for {filename!r}: {response.status_code}"
                    )
                async for chunk in response.aiter_bytes(chunk_size):
                    yield chunk
        except httpx.HTTPError as exc:
            raise ComfyAPIError(
                f"view transport failure for {filename!r}"
            ) from exc

    async def cancel_pending(self, prompt_id: str) -> None:
        try:
            response = await self._client.post(
                self._base + "/queue", json={"delete": [prompt_id]}
            )
        except httpx.HTTPError as exc:
            raise ComfyAPIError(
                f"cancel transport failure (possibly sent): {exc}"
            ) from exc
        if response.status_code >= 400:
            raise ComfyAPIError(f"queue delete rejected: {response.status_code}")

    async def interrupt_running(self) -> None:
        """Raw global interrupt transport. NOT used by Generation cancellation
        (no v0.1 SAFE_SINGLE_FLIGHT interlock); retained only for future
        explicitly-interlocked implementations."""
        response = await self._client.post(self._base + "/interrupt", json={})
        if response.status_code >= 400:
            raise ComfyAPIError(f"interrupt failed: {response.status_code}")

    async def cancel_job(self, prompt_id: str) -> bool | None:
        """Atomic per-job cancellation (M5B-5 product path).

        POST /api/jobs/{prompt_id}/cancel on the pinned deployment:
        server-side ``interrupt_if_running`` holds the queue mutex and the
        interrupt flag is reset per prompt, so the cancel cannot land on a
        successor job; finished/unknown ids are idempotent no-ops. Returns
        True (acted), False (no-op), or None (ambiguous transport failure).
        """
        try:
            response = await self._client.post(
                self._base + f"/api/jobs/{prompt_id}/cancel"
            )
        except httpx.HTTPError:
            return None
        if response.status_code >= 500:
            return None
        if response.status_code >= 400:
            return False  # contract-proven rejection (e.g. malformed id)
        try:
            return wire.normalize_cancel_job_response(response.json())
        except (ValueError, Exception) as exc:  # noqa: BLE001
            raise ComfyAPIError("malformed cancel-job response") from exc

    async def cancel_running_targeted(self, prompt_id: str) -> bool | None:
        """Targeted running cancellation transport.

        Returns True (accepted), False (prompt already terminal/absent =
        TOO_LATE), or None (ambiguous). The target is always the caller's
        persisted prompt_id; this method never selects a target itself.
        """
        try:
            response = await self._client.post(
                self._base + "/interrupt",
                json={"prompt_id": prompt_id},
            )
        except httpx.HTTPError:
            return None
        if response.status_code >= 500:
            return None
        if response.status_code >= 400:
            return False
        try:
            body = response.json()
        except ValueError:
            return None
        if isinstance(body, dict) and body.get("accepted") is False:
            return False
        return True
