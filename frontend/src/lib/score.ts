function bankersRound(value: number): number {
  const floor = Math.floor(value);
  const frac = value - floor;
  if (frac > 0.5) return floor + 1;
  if (frac < 0.5) return floor;
  return floor % 2 === 0 ? floor : floor + 1;
}

export function scoreOutOfTen(raw: number): number {
  let value = Number(raw);
  if (!Number.isFinite(value)) return 0;
  if (value > 10) value = value / 10;
  return Math.max(0, Math.min(10, bankersRound(value)));
}

export function scorePercent(raw: number): number {
  return scoreOutOfTen(raw) * 10;
}
