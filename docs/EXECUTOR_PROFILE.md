# SoloRing v0.1 — Executor Deployment Profile

The characterized dedicated ComfyUI deployment backing the ComfyExecutor
adapter. Every capability below is tied to explicit evidence
(`docs/M5A_EVIDENCE.md`); none is inferred from version arithmetic.

## Executor fingerprint

```text
ComfyUI:       b963f4ad210a42841ab23dfc28a84143a0cce227 (reported 0.33.0)
frontend:      1.49.6
ComfyUI-GGUF:  6ea2651e7df66d7585f6ffee804b20e92fb38b8a
torch:         2.13.0+cu130  (cu126 caused native access violations on this
               RTX 30-series GPU during weight load; see M5B-7 note below)
GPU:           RTX 3080 Ti 12 GB, driver CUDA 13.3
models:        hunyuan-video-i2v-720p-Q4_K_M.gguf (city96),
               clip_l + llava_llama3_fp8_scaled + llava_llama3_vision +
               hunyuan_video_vae_bf16 (Comfy-Org repackaged), all SHA-256
               verified in docs/M5A_EVIDENCE.md M5B-2
```

## Capability profile

```text
mandatory (all LIVE PROVEN):
  prompt_submission      SUPPORTED   (marker canary + real generations)
  queue_observation      SUPPORTED   (keyed-lists dialect, wire-normalized)
  targeted_history       SUPPORTED   (keyed-by-prompt-id; "success" dialect)
  marker_roundtrip       SUPPORTED   (extra_data.soloring survives to history)
  input_upload           SUPPORTED   (exact identity echo, overwrite mode)
  output_view            SUPPORTED   (streamed, bounded, type=output)

telemetry:
  websocket endpoint     SUPPORTED   ({"type":"status",…} first frame)
  real progress/reconnect WS transport integration: DEFERRED — not required
                         for v0.1; HTTP queue + targeted history are the
                         production observation mechanism (authoritative),
                         and this document does NOT claim live WS recovery.

cancellation (LIVE PROVEN, M5B-5):
  pending targeted       SUPPORTED   (POST /queue {delete:[P]} — exact id)
  running targeted       SUPPORTED   (POST /api/jobs/{P}/cancel — server-side
                         interrupt_if_running is atomic under the queue
                         mutex; per-prompt interrupt-flag reset prevents
                         successor leakage)
  targeting              prompt_id
  retry safety           SAFE        (repeat cancel(P) while P' runs → no-op,
                         proven live; unknown id → no-op)
  global /interrupt      UNUSED      (check-then-act; no product path)

persistence (LIVE PROVEN, M5B-6):
  queue across restart   VOLATILE
  history across restart VOLATILE

runtime policy:
  outage grace           30 s   (unreachability never terminates a drive)
  disappearance grace     5 s   (measured live: classified 5.0 s after ready)
  observation cadence     1.0 s (SOLORING_COMFY_OBSERVATION_POLL_SECONDS;
                               measured: 2.0 reads/s, 1.0 s terminal-detection
                               latency; the pre-fix 0.05 s busy loop is gone)
```

## Cancellation mode binding

`SOLORING_COMFY_CANCELLATION_MODE` (`soft_only` default | `targeted`):
`targeted` engages ONLY when a characterization record
(`data/comfy-fingerprint/capability_m5b5.json`) exists whose fingerprint
matches the RUNNING deployment (live version probe) and whose contract
fields are complete (mode TARGETED, retry_safety safe, characterized
endpoint). Any drift — Comfy upgraded, record missing/incomplete, probe
unreachable — **fails closed to SOFT_ONLY** with a loud error log.
`SAFE_SINGLE_FLIGHT` remains unreachable by design (no mechanical global
interlock in v0.1).

## Restart policy (operator notice)

Restarting ComfyUI while SoloRing has active work **will interrupt that
work**: this deployment loses the running queue, the pending queue, and all
history on process restart. SoloRing will NOT resubmit those consumed
attempts; each affected Generation classifies as interruption-class
(`EXECUTOR_JOB_LOST` after the disappearance grace) and a fresh user retry
creates a NEW Generation/attempt. This is a characterized property of the
executor, not a SoloRing defect.

## Presentation contract note

Outputs are animated WebP (SaveAnimatedWEBP). SoloRing's M1 media detector
honestly reports `detected_media_type = null` for WebP (no detector lie);
the captured LOGICAL output kind (`video`, from the immutable workflow spec)
drives preview at the presentation boundary. Verified live in the real UI:
the take renders (848×480 decoded), approval and canon re-evaluation work.

## M5B-7 stability note (honest)

The first four final-gate attempts crashed the executor with a native
`access violation` during CLIP-vision weight load. Root cause: torch
**cu126** wheels on this RTX 30-series GPU + driver combination (the 20-series-or-newer code path) (ComfyUI 0.33
warns "pytorch with cu130 or higher required"). Every crash was classified
correctly by SoloRing (outage tolerance → `EXECUTOR_UNAVAILABLE`, never a
resubmission). Upgrading the ComfyUI venv to torch 2.13.0+**cu130** resolved
it; the final render then completed cleanly. The fingerprint above records
cu130.
