export const PHILIPPINE_TIME_ZONE = "Asia/Manila";

type DateTimeValue = Date | number | string;

const HAS_TIME_ZONE = /(Z|[+-]\d{2}:?\d{2})$/i;

/**
 * Backend timestamps are stored in UTC, but legacy API responses can omit the
 * trailing Z. Normalize those values before formatting so browsers do not
 * mistake UTC for their local wall-clock time.
 */
export function parseServerDateTime(value: DateTimeValue): Date {
  if (value instanceof Date || typeof value === "number") {
    return new Date(value);
  }

  const trimmed = value.trim();
  const normalized = HAS_TIME_ZONE.test(trimmed) ? trimmed : `${trimmed}Z`;
  return new Date(normalized);
}

export function formatPhilippineDateTime(
  value: DateTimeValue,
  options: Intl.DateTimeFormatOptions = {},
): string {
  const date = parseServerDateTime(value);
  if (Number.isNaN(date.getTime())) {
    return typeof value === "string" ? value : "Invalid date";
  }

  const defaultOptions: Intl.DateTimeFormatOptions = options.dateStyle || options.timeStyle
    ? {}
    : {
        year: "numeric",
        month: "numeric",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
      };

  return new Intl.DateTimeFormat("en-PH", {
    ...defaultOptions,
    ...options,
    timeZone: PHILIPPINE_TIME_ZONE,
  }).format(date);
}
