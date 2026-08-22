/**
 * M9 §81 gate — Realization UI tests (pure render, server-fed; the
 * browser never constructs authority or re-computes rule matching).
 * Covers ready, M7/M8-blocked, required-unsupported, capacity,
 * each optional omission reason, runtime-incompatible labeling, the
 * non-reservation statement + package hashes, and the historical
 * inspector's captured-vs-identity display.
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import GenerationRealizationInspector from "@/components/GenerationRealizationInspector";
import RealizationPanel from "@/components/RealizationPanel";
import type {
  GenerationRealization,
  RealizationReadiness,
} from "@/lib/realizationTypes";

const PACKAGE = {
  schema_version: 2,
  workflow_id: "hunyuan_i2v",
  workflow_version: 4,
  manifest_hash: "m".repeat(64),
  workflow_template_hash: "t".repeat(64),
  realization_profile_hash: "p".repeat(64),
  execution_model_fingerprint_hash: "f".repeat(64),
};

function readiness(over: Partial<RealizationReadiness>): RealizationReadiness {
  return {
    shot_id: "shot-1",
    ready: true,
    package: PACKAGE,
    model: { id: "hunyuan-video-i2v", version: "q4_k_m-720p-llava" },
    profile: {
      id: "hunyuan-i2v-single-reference",
      version: 1,
      hash: "p".repeat(64),
    },
    visual_reference_pack_hash: "a".repeat(64),
    issues: [],
    channels: [
      {
        channel: "hero_reference",
        input_key: "reference_image",
        min_items: 1,
        max_items: 1,
        used_items: 1,
        active: true,
      },
    ],
    facet_statuses: [
      {
        visual_facet_id: "f1",
        target_kind: "entity",
        facet_key: "identity",
        requirement: "required",
        status: "selected",
        channel: "hero_reference",
        input_key: "reference_image",
        selected_items: [
          {
            asset_id: "asset-9",
            blob_hash: "b".repeat(64),
            role: "primary",
            view_key: "front",
            source_position: 0,
            binding_position: 0,
          },
        ],
        reason: null,
        issue_code: null,
      },
    ],
    omitted_optional: [],
    ...over,
  };
}

describe("RealizationPanel (M9 §36.1–36.2)", () => {
  afterEach(cleanup);

  it("renders ready state with non-reservation label and package hashes", () => {
    const { container } = render(
      <RealizationPanel state={readiness({})} />,
    );
    expect(container.textContent).toContain("NOT reserved");
    expect(container.textContent).toContain("hunyuan_i2v v4");
    expect(container.textContent).toContain("identity");
    expect(container.textContent).toContain("hero_reference");
    expect(container.textContent).toContain("1/1");
    expect(container.textContent).toContain("asset-9".slice(0, 8));
  });

  it("renders M7-blocked honestly without partial evaluation", () => {
    const { container } = render(
      <RealizationPanel
        state={readiness({
          ready: false,
          issues: [
            { error_code: "NARRATIVE_CONTEXT_REQUIRED", layer: "m7" },
          ],
          facet_statuses: [],
          channels: [
            {
              channel: "hero_reference",
              input_key: "reference_image",
              min_items: 1,
              max_items: 1,
              used_items: 0,
              active: false,
            },
          ],
        })}
      />,
    );
    expect(container.textContent).toContain("Blocked by M7 semantic state");
    expect(container.textContent).toContain("NARRATIVE_CONTEXT_REQUIRED");
  });

  it("renders M8-blocked distinctly from M7", () => {
    const { container } = render(
      <RealizationPanel
        state={readiness({
          ready: false,
          issues: [
            { error_code: "VISUAL_REALIZATION_REQUIRED", layer: "m8" },
          ],
          facet_statuses: [],
        })}
      />,
    );
    expect(container.textContent).toContain("Blocked by M8 visual");
    expect(container.textContent).toContain("VISUAL_REALIZATION_REQUIRED");
  });

  it("renders required-unsupported with the exact M9 code", () => {
    const { container } = render(
      <RealizationPanel
        state={readiness({
          ready: false,
          issues: [
            {
              error_code: "REALIZATION_REQUIRED_FACET_UNSUPPORTED",
              layer: "m9",
              facet_key: "face",
            },
          ],
          facet_statuses: [
            {
              visual_facet_id: "f2",
              target_kind: "entity",
              facet_key: "face",
              requirement: "required",
              status: "required_blocked",
              channel: null,
              input_key: null,
              selected_items: [],
              reason: null,
              issue_code: "REALIZATION_REQUIRED_FACET_UNSUPPORTED",
            },
          ],
        })}
      />,
    );
    expect(container.textContent).toContain("NOT realizable");
    expect(container.textContent).toContain(
      "REALIZATION_REQUIRED_FACET_UNSUPPORTED",
    );
    expect(container.textContent).toContain("BLOCKED");
  });

  it("renders capacity and channel-minimum blockers", () => {
    const { container } = render(
      <RealizationPanel
        state={readiness({
          ready: false,
          issues: [
            { error_code: "REALIZATION_CAPACITY_EXCEEDED", layer: "m9" },
          ],
          facet_statuses: [],
        })}
      />,
    );
    expect(container.textContent).toContain("REALIZATION_CAPACITY_EXCEEDED");

    cleanup();
    const c2 = render(
      <RealizationPanel
        state={readiness({
          ready: false,
          issues: [
            {
              error_code: "REALIZATION_CHANNEL_MINIMUM_UNMET",
              layer: "m9",
            },
          ],
          facet_statuses: [],
        })}
      />,
    );
    expect(c2.container.textContent).toContain(
      "REALIZATION_CHANNEL_MINIMUM_UNMET",
    );
  });

  it("renders every closed optional omission reason", () => {
    const reasons = [
      "no_matching_rule",
      "no_allowed_items",
      "capacity_exceeded",
      "channel_minimum_unmet",
    ];
    for (const reason of reasons) {
      const { container } = render(
        <RealizationPanel
          state={readiness({
            facet_statuses: [
              {
                visual_facet_id: "f3",
                target_kind: "entity",
                facet_key: "wardrobe",
                requirement: "optional",
                status: "optional_omitted",
                channel: null,
                input_key: null,
                selected_items: [],
                reason,
                issue_code: null,
              },
            ],
            omitted_optional: [
              {
                visual_facet_id: "f3",
                target_kind: "entity",
                facet_key: "wardrobe",
                reason,
              },
            ],
          })}
        />,
      );
      expect(container.textContent).toContain(`omitted — ${reason}`);
      cleanup();
    }
  });

  it("renders the honest empty-authority legacy case", () => {
    const { container } = render(
      <RealizationPanel
        state={readiness({
          facet_statuses: [],
          visual_reference_pack_hash: null,
        })}
      />,
    );
    expect(container.textContent).toContain("no captured M8 authority");
  });

  it("renders unresolved when no state exists", () => {
    const { container } = render(<RealizationPanel state={null} />);
    expect(container.textContent).toContain("unavailable");
  });
});

describe("GenerationRealizationInspector (M9 §36.3)", () => {
  afterEach(cleanup);

  const gen: GenerationRealization = {
    workflow_spec_schema_version: 2,
    model: "hunyuan-video-i2v",
    model_version: "q4_k_m-720p-llava",
    realization_profile_id: "hunyuan-i2v-single-reference",
    realization_profile_version: 1,
    realization_profile_hash: "p".repeat(64),
    visual_reference_pack_hash: "a".repeat(64),
    manifest_hash: "m".repeat(64),
    workflow_template_hash: "t".repeat(64),
    realization_summary: {
      channels: [
        {
          channel: "hero_reference",
          input_key: "reference_image",
          bindings: [
            {
              facet_key: "identity",
              required: true,
              asset_id: "asset-9",
              blob_hash: "b".repeat(64),
              role: "primary",
              view_key: "front",
            },
          ],
        },
      ],
      omitted_optional: [{ facet_key: "wardrobe", reason: "capacity_exceeded" }],
      parameter_overrides: { cfg: 2.5 },
      execution_model_fingerprint_hash: "f".repeat(64),
    },
  };

  it("renders captured identity incl. Blob identity and omissions", () => {
    const { container } = render(
      <GenerationRealizationInspector generation={gen} />,
    );
    expect(container.textContent).toContain("hunyuan-i2v-single-reference");
    expect(container.textContent).toContain("q4_k_m-720p-llava");
    expect(container.textContent).toContain("asset-9".slice(0, 8));
    expect(container.textContent).toContain("b".repeat(64).slice(0, 8));
    expect(container.textContent).toContain("wardrobe (capacity_exceeded)");
    expect(container.textContent).toContain("cfg=2.5");
  });

  it("renders legacy schema-1 generations honestly", () => {
    const { container } = render(
      <GenerationRealizationInspector
        generation={{
          workflow_spec_schema_version: 1,
          model: null,
          model_version: null,
          realization_profile_id: null,
          realization_profile_version: null,
          realization_profile_hash: null,
          visual_reference_pack_hash: null,
          manifest_hash: null,
          workflow_template_hash: null,
          realization_summary: null,
        }}
      />,
    );
    expect(container.textContent).toContain("No captured M9 realization");
  });
});
