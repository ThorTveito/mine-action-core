import type { MonthlyClearance } from "./types";

export const fmtArea = (m2: number): string =>
  m2 >= 1e6 ? `${(m2 / 1e6).toFixed(2)} km²` : `${Math.round(m2).toLocaleString()} m²`;

export const fmtMonth = (yyyymm: string): string => {
  const [y, m] = yyyymm.split("-");
  return new Date(Number(y), Number(m) - 1, 1).toLocaleString("en", {
    month: "short",
    year: "2-digit",
  });
};

/** Continuous months from first to last, zero-filled, so the time axis is not distorted. */
export function fillMonths(data: MonthlyClearance[]): MonthlyClearance[] {
  if (data.length === 0) return data;
  const byMonth = new Map(data.map((d) => [d.month, d]));
  const [y0, m0] = data[0].month.split("-").map(Number);
  const [y1, m1] = data[data.length - 1].month.split("-").map(Number);
  const out: MonthlyClearance[] = [];
  for (let y = y0, m = m0; y < y1 || (y === y1 && m <= m1); m === 12 ? ((m = 1), y++) : m++) {
    const key = `${y}-${String(m).padStart(2, "0")}`;
    out.push(byMonth.get(key) ?? { month: key, cleared_area_m2: 0, items_destroyed: 0, items_found: 0 });
  }
  return out;
}

