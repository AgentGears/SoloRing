"""Authoritative WAVE inspection for M17A candidate audio (frozen R5
§5). One `sample` means one PCM sample FRAME across all channels.
Metadata is inspected from bytes, never trusted from callers.
"""

from __future__ import annotations

import struct

from soloring.errors import SoloRingError, ErrorCode

_RIFF = b"RIFF"
_WAVE = b"WAVE"
_FMT_PCM = 1


def _reject(reason: str) -> SoloRingError:
    return SoloRingError(ErrorCode.VALIDATION_ERROR,
                         f"INVALID_AUDIO_BYTES: {reason}",
                         status_code=422, details={"reason": reason})


def _unsupported(reason: str) -> SoloRingError:
    return SoloRingError(ErrorCode.VALIDATION_ERROR,
                         f"UNSUPPORTED_VOCAL_MEDIA: {reason}",
                         status_code=422, details={"reason": reason})


def inspect_wave(data: bytes) -> dict:
    """Validate a RIFF/WAVE uncompressed-PCM blob and derive the
    authoritative sample rate + sample-frame count."""
    if len(data) < 12 or data[0:4] != _RIFF or data[8:12] != _WAVE:
        raise _unsupported("not a RIFF/WAVE container")
    pos = 12
    fmt_seen = False
    channels = sample_rate = bits = None
    data_bytes = None
    while pos + 8 <= len(data):
        chunk_id = data[pos:pos + 4]
        (chunk_size,) = struct.unpack_from("<I", data, pos + 4)
        body = data[pos + 8: pos + 8 + chunk_size]
        if len(body) < chunk_size:
            raise _reject(f"truncated chunk {chunk_id!r}")
        if chunk_id == b"fmt ":
            if chunk_size < 16:
                raise _reject("fmt chunk too small")
            audio_format, ch, rate, _, _, bits_per = struct.unpack_from(
                "<HHIIHH", body, 0)
            if audio_format != _FMT_PCM:
                raise _unsupported(
                    f"audio format {audio_format} is not uncompressed "
                    "PCM")
            if ch < 1:
                raise _reject("channel count must be >= 1")
            if bits_per % 8 != 0 or bits_per < 8:
                raise _reject("sample width must be whole bytes >= 1")
            channels, sample_rate, bits = ch, rate, bits_per
            fmt_seen = True
        elif chunk_id == b"data":
            data_bytes = chunk_size
        pos += 8 + chunk_size + (chunk_size & 1)
    if not fmt_seen:
        raise _reject("missing fmt chunk")
    if data_bytes is None:
        raise _reject("missing data chunk")
    frame_bytes = (channels * bits) // 8
    if frame_bytes == 0 or data_bytes % frame_bytes != 0:
        raise _reject("data chunk is not a whole number of frames")
    if sample_rate < 1:
        raise _reject("sample rate must be >= 1")
    frames = data_bytes // frame_bytes
    if frames < 1:
        raise _reject("zero sample frames")
    return {"sample_rate_hz": sample_rate, "sample_frame_count": frames,
            "channels": channels, "bits_per_sample": bits,
            "byte_length": len(data)}
