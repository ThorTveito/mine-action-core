export const fmtArea = (m2: number): string =>
  m2 >= 1e6 ? `${(m2 / 1e6).toFixed(2)} km²` : `${Math.round(m2).toLocaleString()} m²`;

export const fmtMonth = (yyyymm: string): string => {
  const [y, m] = yyyymm.split("-");
  return new Date(Number(y), Number(m) - 1, 1).toLocaleString("en", {
    month: "short",
    year: "2-digit",
  });
};
