import type { HazardStatus } from "./types";

// Single source of truth for status colours (map layers and legend).
export const STATUS_ORDER: HazardStatus[] = [
  "suspected",
  "confirmed",
  "in_clearance",
  "released",
  "cancelled",
];

export const STATUS_COLOR: Record<HazardStatus, string> = {
  suspected: "#c98d00",
  confirmed: "#d64545",
  in_clearance: "#3b82f6",
  released: "#2f9e60",
  cancelled: "#8a94a3",
};

export const STATUS_LABEL: Record<HazardStatus, string> = {
  suspected: "Suspected",
  confirmed: "Confirmed",
  in_clearance: "In clearance",
  released: "Released",
  cancelled: "Cancelled",
};
