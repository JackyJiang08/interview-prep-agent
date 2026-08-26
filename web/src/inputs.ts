// What the landing page knows about its own inputs: which format a pasted
// or dropped evidence file is in, how large each input may be, and how a
// file becomes text. All of it is pure and mirrors the server, which stays
// the authority — a refusal here saves a round trip, it never replaces one.

export type EvidenceFormat = "yaml" | "markdown";

// The server's defaults, one per field. Names are the request-body fields.
export const INPUT_CEILINGS = {
  jd_text: 20_000,
  evidence_text: 50_000,
  round_text: 2_000,
  research_text: 20_000,
} as const;

export type BoundedField = keyof typeof INPUT_CEILINGS;

const FIELD_LABELS: Record<BoundedField, string> = {
  jd_text: "the job posting",
  evidence_text: "the evidence",
  round_text: "the round description",
  research_text: "the research notes",
};

// The same refusal the server would send, in the same tone, before the
// request leaves the browser.
export function overCeiling(field: BoundedField, length: number): string | null {
  const ceiling = INPUT_CEILINGS[field];
  if (length <= ceiling) return null;
  return `${FIELD_LABELS[field]} exceeds the ${ceiling.toLocaleString("en-US")}-character ceiling`;
}

// An evidence corpus is a YAML sequence of mappings, each carrying at least
// `id` and `summary`, optionally wrapped in an `evidence:` mapping; a JSON
// corpus is the same shape and is valid YAML. Anything else — a resume, a
// list of bullets, prose — is read as markdown, whose parser accepts any
// text. The check is structural rather than a full parse: the first content
// line must open a sequence item or the wrapper key, and a `summary:` key
// must appear as a mapping entry within the sequence.
export function detectEvidenceFormat(text: string): EvidenceFormat {
  const lines = text
    .split(/\r?\n/)
    .filter((line) => line.trim() !== "" && !line.trimStart().startsWith("#"));
  if (lines.length === 0) return "markdown";

  const first = lines[0].trim();
  if (first.startsWith("[") || first.startsWith("{")) return "yaml";

  const opensSequence = /^-\s+\w[\w-]*\s*:/.test(first);
  const opensWrapper = /^evidence\s*:\s*$/.test(first);
  if (!opensSequence && !opensWrapper) return "markdown";

  const hasSummaryEntry = lines.some((line) => /^\s*(-\s+)?summary\s*:/.test(line));
  const hasIdEntry = lines.some((line) => /^\s*(-\s+)?id\s*:/.test(line));
  return hasSummaryEntry && hasIdEntry ? "yaml" : "markdown";
}

export const POSTING_EXTENSIONS = [".txt", ".md"];
export const EVIDENCE_EXTENSIONS = [".pdf", ".md", ".markdown", ".yaml", ".yml"];

export function isPdf(name: string): boolean {
  return acceptedFile(name, [".pdf"]);
}

// What the page calls a loaded resume: the shape the server will read it
// as, in the reader's words. The format decides the label; the filename only
// adds what the format cannot see - that the text came out of a PDF.
export function describeKind(format: EvidenceFormat, filename: string | null = null): string {
  if (format === "yaml") return "a YAML evidence list";
  return filename !== null && isPdf(filename) ? "a resume, text read from the PDF" : "a resume";
}

export function acceptedFile(name: string, extensions: string[]): boolean {
  const lower = name.toLowerCase();
  return extensions.some((extension) => lower.endsWith(extension));
}

export function describeExtensions(extensions: string[]): string {
  if (extensions.length === 1) return extensions[0];
  return `${extensions.slice(0, -1).join(", ")} or ${extensions[extensions.length - 1]}`;
}

// Reads one file as text, refusing the wrong kind or an oversized one with
// the same wording the server would use. Returns the text, or the refusal.
export async function readTextFile(
  file: File,
  extensions: string[],
  field: BoundedField,
): Promise<{ text: string } | { refusal: string }> {
  if (!acceptedFile(file.name, extensions)) {
    return { refusal: `that file is not ${describeExtensions(extensions)}; nothing was read` };
  }
  const text = await file.text();
  const refusal = overCeiling(field, text.length);
  return refusal === null ? { text } : { refusal: `${refusal}; nothing was read` };
}
