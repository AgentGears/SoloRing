/**
 * RR21-M17CC-01 — the exact web round-trip for authoritative Shot
 * duration (HIGH correction battery, frontend half).
 *
 * The lawful backend domain is [0, 2^63-1]; JavaScript `number`
 * cannot carry it (2^53+1 already rounds), so authoritative duration
 * crosses the web boundary as the additive canonical decimal-string
 * coordinate `duration_ms_dec` and stays a string end to end —
 * display, edit initialization, equality, and submission NEVER pass
 * through `Number()`/IEEE-754. These tests prove the grammar/domain
 * helper, the exact display in the editor and the timeline, the
 * exact string on the PATCH wire for both an untouched and a
 * deliberately edited duration, and the JS-number corroboration
 * (why the correction matters). A 2^53-only test cannot expose the
 * defect (exactly representable); the adversaries are 2^53+1 and
 * 2^63-1.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  durationInput,
  durationToTransport,
  isCanonicalDurationDec,
  SQLITE_INT_MAX_DEC,
  timeBelowExactDuration,
} from "@/lib/exactDuration";

const STRONG = "9007199254740993"; // 2^53 + 1 (JS rounds to ...992)
const ROUNDED = "9007199254740992"; // what IEEE-754 silently makes of it
const OTHER_UNSAFE = "9007199254740995";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: () => undefined }),
}));

describe("RR21 exact decimal grammar + domain", () => {
  it("accepts the canonical forms and rejects every alias", () => {
    expect(isCanonicalDurationDec("0")).toBe(true);
    expect(isCanonicalDurationDec(STRONG)).toBe(true);
    expect(isCanonicalDurationDec(SQLITE_INT_MAX_DEC)).toBe(true);
    for (const bad of [
      "+1", "-1", "1.0", " 1", "1 ", "01", "1e3", "", "0x1",
      "9223372036854775808", // SQLITE_INT_MAX + 1
      "99999999999999999999999",
    ]) {
      expect(isCanonicalDurationDec(bad)).toBe(false);
    }
  });

  it("transport: unset → null; exact strings pass through untouched", () => {
    expect(durationToTransport("")).toBeNull();
    expect(durationToTransport(STRONG)).toBe(STRONG);
    expect(durationToTransport(SQLITE_INT_MAX_DEC))
      .toBe(SQLITE_INT_MAX_DEC);
    expect(() => durationToTransport("1.0")).toThrow();
    expect(() => durationToTransport("01")).toThrow();
  });

  it("RR22: noncanonical values never normalize — no trimming", () => {
    // only the LITERAL empty string is unset; every other
    // noncanonical form (whitespace aliases included) rejects
    expect(durationToTransport("")).toBeNull();
    for (const bad of [" 1", "1 ", "  ", "\t1", "01",
      "+1", "-1", "1.0", "1e3"]) {
      expect(() => durationToTransport(bad)).toThrow();
    }
    // the exact valid string still passes through untouched
    expect(durationToTransport("1")).toBe("1");
    expect(durationToTransport("0")).toBe("0");
    expect(durationToTransport(STRONG)).toBe(STRONG);
  });

  it("input initialization comes from the string, not a number", () => {
    expect(durationInput(null)).toBe("");
    expect(durationInput(undefined)).toBe("");
    expect(durationInput(STRONG)).toBe(STRONG);
  });

  it("the timeline guard compares exactly (BigInt, not number)", () => {
    expect(timeBelowExactDuration(1, STRONG)).toBe(true);
    // The decisive exactness proof: event time ...992 against the
    // exact duration ...993 — a JS-number comparison would see
    // Number("...993") === ...992 and refuse "at the end"; the
    // exact decimal guard correctly admits it as strictly interior
    expect(timeBelowExactDuration(9007199254740992, STRONG))
      .toBe(true);
    expect(timeBelowExactDuration(9007199254740992, ROUNDED))
      .toBe(false);
  });
});

describe("RR21 JS-number corroboration (why the correction matters)", () => {
  it("Number() silently rounds the lawful authority", () => {
    expect(Number(STRONG)).toBe(Number(ROUNDED));
    expect(Number(STRONG)).not.toBe(Number(OTHER_UNSAFE));
    expect(String(Number(STRONG))).toBe(ROUNDED);
  });
});

function shotDetailFixture(durationDec: string | null) {
  return {
    id: "shot-1",
    project_id: "p1",
    shot_number: 1,
    title: "Original title",
    subject: "s",
    action: null,
    environment: null,
    framing: null,
    camera_motion: null,
    lens: null,
    mood: null,
    duration_ms: durationDec === null ? null : Number(durationDec),
    duration_ms_dec: durationDec,
    approved_take_id: null,
    working_snapshot_hash: null,
    working_state_differs_from_approved: null,
    semantic_dependencies: [],
    continuity_ready: false,
    continuity_state_ready: true,
    readiness_issues: [],
    updated_at: "2026-10-06T00:00:00Z",
  };
}

describe("RR21 ShotForm exact round-trip", () => {
  it("renders the EXACT decimal in the duration input", async () => {
    const ShotForm = (await import("@/components/ShotForm")).default;
    render(<ShotForm shot={shotDetailFixture(STRONG) as never} />);
    const input = await screen.findByDisplayValue(STRONG);
    expect(input).not.toBeNull();
    expect(screen.queryByDisplayValue(ROUNDED)).toBeNull();
  });

  it("submits the untouched exact string on an unrelated-field save", async () => {
    const ShotForm = (await import("@/components/ShotForm")).default;
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => shotDetailFixture(STRONG),
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ShotForm shot={shotDetailFixture(STRONG) as never} />);
    const title = screen.getByDisplayValue("Original title");
    fireEvent.change(title, { target: { value: "Renamed" } });
    fireEvent.click(screen.getByRole("button", { name: /save shot/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [, init] = fetchMock.mock.calls[0] as unknown as [
      string, RequestInit,
    ];
    const payload = JSON.parse(String(init.body));
    // the EXACT untouched decimal string — never Number(...) of it
    expect(payload.duration_ms).toBe(STRONG);
    expect(payload.title).toBe("Renamed");
  });

  it("submits a deliberately edited exact unsafe integer exactly", async () => {
    const ShotForm = (await import("@/components/ShotForm")).default;
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => shotDetailFixture(OTHER_UNSAFE),
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ShotForm shot={shotDetailFixture(STRONG) as never} />);
    const input = screen.getByDisplayValue(STRONG);
    fireEvent.change(input, { target: { value: OTHER_UNSAFE } });
    fireEvent.click(screen.getByRole("button", { name: /save shot/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [, init] = fetchMock.mock.calls[0] as unknown as [
      string, RequestInit,
    ];
    expect(JSON.parse(String(init.body)).duration_ms)
      .toBe(OTHER_UNSAFE);
  });

  it("refuses an ambiguous alias client-side (typed, no wire call)", async () => {
    const ShotForm = (await import("@/components/ShotForm")).default;
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<ShotForm shot={shotDetailFixture(STRONG) as never} />);
    const input = screen.getByDisplayValue(STRONG);
    fireEvent.change(input, { target: { value: "1.0" } });
    fireEvent.click(screen.getByRole("button", { name: /save shot/i }));
    // the typed client-side refusal banner appears (the message may
    // be split across elements — match on the banner container)
    await waitFor(
      () =>
        document.querySelector(".error-banner")?.textContent ?? "",
      { timeout: 4000 },
    );
    await waitFor(() => {
      const banner = document.querySelector(".error-banner");
      expect(banner?.textContent ?? "").toMatch(
        /whole number|canonical|duration/i);
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
