const DISPLAY_ACRONYMS = new Set(["ai", "asr", "id", "kp", "ner", "nlp", "php", "pnp", "vawc", "wcpd"]);

export function formatDisplayLabel(value: string) {
  return value
    .trim()
    .replaceAll("_", " ")
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => DISPLAY_ACRONYMS.has(word.toLowerCase())
      ? word.toUpperCase()
      : `${word.charAt(0).toUpperCase()}${word.slice(1).toLowerCase()}`)
    .join(" ");
}

export function humanizeDisplayText(value: string) {
  return value.replace(
    /\b[a-z0-9]+(?:_[a-z0-9]+)+\b/gi,
    (token) => formatDisplayLabel(token),
  );
}

export function formatDisplayList(values: string[]) {
  return values.map((value) => humanizeDisplayText(value)).join(", ");
}
