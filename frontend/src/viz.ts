// Chart colours. Validated with the dataviz palette checker (light surface):
// categorical slots in fixed order, a single-hue ordinal ramp for the choropleth.
import type { ReleaseMethod } from "./types";

export const SERIES = "#0f766e"; // single-series charts; deliberately not a status colour

export const CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a"] as const;

export const RELEASE_ORDER: ReleaseMethod[] = ["cancelled", "reduced", "cleared"];
export const RELEASE_COLOR: Record<ReleaseMethod, string> = {
  cancelled: CATEGORICAL[0],
  reduced: CATEGORICAL[1],
  cleared: CATEGORICAL[2],
};
export const RELEASE_LABEL: Record<ReleaseMethod, string> = {
  cancelled: "Cancelled (non-technical survey)",
  reduced: "Reduced (technical survey)",
  cleared: "Cleared",
};

export const OUTCOME_COLOR = { injured: CATEGORICAL[0], killed: CATEGORICAL[1] } as const;

// Ordinal blue ramp, light to dark (passes monotone lightness and light-end contrast).
export const SEQUENTIAL = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"] as const;
export const NO_DATA = "#e5e7eb";
