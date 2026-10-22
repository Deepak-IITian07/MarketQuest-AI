// Display helpers. Kept in one place so every panel formats numbers the same way.

const inrFull = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const inrCompact = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  notation: "compact",
  maximumFractionDigits: 1,
});

const inrWhole = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

const plain = new Intl.NumberFormat("en-IN");

export function formatINR(value: number): string {
  return inrFull.format(value);
}

export function formatINRCompact(value: number): string {
  return inrCompact.format(value);
}

export function formatINRWhole(value: number): string {
  return inrWhole.format(value);
}

export function formatCount(value: number): string {
  return plain.format(Math.round(value));
}

/** A decimal fraction (0.0125) as a percentage string ("1.25%"). */
export function formatFractionAsPct(fraction: number, digits = 2): string {
  return `${(fraction * 100).toFixed(digits)}%`;
}

/** A value that is already in percent (4.2) as a percentage string ("4.20%"). */
export function formatPct(percent: number, digits = 2): string {
  return `${percent.toFixed(digits)}%`;
}

/** A percentage with an explicit sign, for deltas. */
export function formatSignedPct(percent: number, digits = 2): string {
  const sign = percent > 0 ? "+" : "";
  return `${sign}${percent.toFixed(digits)}%`;
}

/**
 * Parse a backend ISO date (YYYY-MM-DD) and format it for display.
 * The date is pinned to UTC so a browser in a negative-offset timezone
 * cannot show the previous day.
 */
export function formatDate(iso: string, options?: Intl.DateTimeFormatOptions): string {
  const parsed = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return iso;
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
    ...options,
  }).format(parsed);
}

/** e.g. "7 Sep 2026" */
export function formatDateLong(iso: string): string {
  return formatDate(iso, { day: "numeric", month: "short", year: "numeric" });
}
