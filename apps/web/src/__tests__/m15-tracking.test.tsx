import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import M15TrackingBadge from "@/components/M15TrackingBadge";

afterEach(cleanup);

describe("pinned_and_track_compatible_modes_are_explicit", () => {
  it("renders never-authored absence as Pinned (version 0)", () => {
    const onChange = vi.fn();
    render(
      <M15TrackingBadge
        mode="PINNED"
        policyVersion={0}
        busy={false}
        onChange={onChange}
      />,
    );
    expect(screen.getByTestId("tracking-mode").textContent).toContain(
      "Pinned",
    );
    expect(screen.getByTestId("tracking-version").textContent).toContain("0");
  });

  it("renders the authored TRACK_COMPATIBLE state with its version", () => {
    render(
      <M15TrackingBadge
        mode="TRACK_COMPATIBLE"
        policyVersion={1}
        busy={false}
        onChange={() => {}}
      />,
    );
    expect(screen.getByTestId("tracking-mode").textContent).toContain(
      "Track compatible",
    );
    expect(screen.getByTestId("tracking-version").textContent).toContain("1");
  });

  it("labels the offer semantics: assess explicitly, never auto-follow", () => {
    render(
      <M15TrackingBadge
        mode="TRACK_COMPATIBLE"
        policyVersion={2}
        busy={false}
        onChange={() => {}}
      />,
    );
    expect(screen.getByTestId("tracking-note").textContent).toContain(
      "Offers newer revisions for explicit assessment",
    );
    expect(screen.getByTestId("tracking-note").textContent).not.toContain(
      "automatic",
    );
  });

  it("switching mode requests the expected version and refuses stale input", () => {
    const onChange = vi.fn();
    render(
      <M15TrackingBadge
        mode="PINNED"
        policyVersion={0}
        busy={false}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByTestId("tracking-toggle"));
    expect(onChange).toHaveBeenCalledWith("TRACK_COMPATIBLE", 0);
  });
});
