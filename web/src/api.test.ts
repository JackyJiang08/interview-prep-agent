import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createSession,
  describeTransportFailure,
  encodeBase64,
  EvidenceRefusal,
  extractResume,
  previewEvidence,
  streamUrl,
} from "./api";

describe("the socket url", () => {
  it("opens wss on an https page and ws on an http one, on the page's host", () => {
    expect(streamUrl("abc", { protocol: "https:", host: "demo.example.org" })).toBe(
      "wss://demo.example.org/api/sessions/abc/stream",
    );
    expect(streamUrl("abc", { protocol: "http:", host: "127.0.0.1:8000" })).toBe(
      "ws://127.0.0.1:8000/api/sessions/abc/stream",
    );
  });
});

describe("session creation", () => {
  afterEach(() => vi.unstubAllGlobals());

  const body = { mode: "demo" as const, demo_id: "mixed-clarifications" };

  it("returns the session id on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ session_id: "s-1" }), { status: 201 })),
    );
    expect(await createSession(body)).toBe("s-1");
  });

  it("surfaces the server's own refusal wording", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({ error: { category: "unknown_demo", message: "no demo named 'x'" } }),
            { status: 404 },
          ),
      ),
    );
    await expect(createSession(body)).rejects.toThrow("no demo named 'x'");
  });

  it("turns a proxy's html error page into a plain sentence, never a parse error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("<html>504 Gateway Timeout</html>", { status: 504 })),
    );
    await expect(createSession(body)).rejects.toThrow(
      "the server answered with status 504 instead of a session; try again in a moment",
    );
  });

  it("refuses a success without a session id rather than starting nothing", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 201 })));
    await expect(createSession(body)).rejects.toThrow("without a session id");
  });

  it("turns a dropped connection into a plain sentence", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("fetch failed");
      }),
    );
    await expect(createSession(body)).rejects.toThrow("never reached the server");
  });

  it("times out a request the platform never answers, naming the likely cause", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init.signal?.addEventListener("abort", () => reject(init.signal?.reason));
          }),
      ),
    );
    await expect(createSession(body, 20)).rejects.toThrow("did not answer within a minute");
  });

  it("recognizes a timeout wrapped as the cause of another error", () => {
    const wrapped = new TypeError("fetch failed", { cause: { name: "TimeoutError" } });
    expect(describeTransportFailure(wrapped)).toContain("did not answer");
    expect(describeTransportFailure(new TypeError("fetch failed"))).toContain("never reached");
  });
});

describe("pdf extraction", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends the file's bytes as base64 with its name and returns the text", async () => {
    const calls: { url: string; body: unknown }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init: RequestInit) => {
        calls.push({ url, body: JSON.parse(String(init.body)) });
        return new Response(JSON.stringify({ text: "## Skills\n- SQL", pages: 1 }), {
          status: 200,
        });
      }),
    );
    const file = new File([new Uint8Array([37, 80, 68, 70, 0, 255])], "Resume.PDF");
    expect(await extractResume(file)).toEqual({ text: "## Skills\n- SQL", pages: 1 });
    expect(calls[0].url).toBe("/api/extract-resume");
    expect(calls[0].body).toEqual({ filename: "Resume.PDF", content_base64: "JVBERgD/" });
  });

  it("surfaces the server's refusal for a scan, in its own words", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              error: {
                category: "no_text_layer",
                message: "this PDF has no text layer - it is likely a scan; paste the resume text instead",
              },
            }),
            { status: 422 },
          ),
      ),
    );
    await expect(extractResume(new File(["x"], "scan.pdf"))).rejects.toThrow(
      "paste the resume text instead",
    );
  });

  it("turns a non-json failure into a plain sentence", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>502</html>", { status: 502 })));
    await expect(extractResume(new File(["x"], "resume.pdf"))).rejects.toThrow(
      "status 502 instead of the resume text",
    );
  });

  it("encodes bytes of any length, including past one chunk", () => {
    expect(encodeBase64(new Uint8Array([]))).toBe("");
    expect(encodeBase64(new Uint8Array([104, 105]))).toBe("aGk=");
    const long = new Uint8Array(0x8000 + 3).fill(65);
    expect(atob(encodeBase64(long)).length).toBe(0x8000 + 3);
  });
});

describe("evidence preview", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("returns the count and the first summaries", async () => {
    const calls: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init: RequestInit) => {
        calls.push(JSON.parse(String(init.body)));
        return new Response(JSON.stringify({ count: 14, summaries: ["a", "b", "c"] }), {
          status: 200,
        });
      }),
    );
    expect(await previewEvidence("## Work\n- a\n", "markdown")).toEqual({
      count: 14,
      summaries: ["a", "b", "c"],
    });
    expect(calls[0]).toEqual({ evidence_text: "## Work\n- a\n", evidence_format: "markdown" });
  });

  it("surfaces an empty read as a refusal with its category, so Start can stay disabled", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              error: { category: "empty_evidence", message: "the resume contains no readable content" },
            }),
            { status: 422 },
          ),
      ),
    );
    const failure = await previewEvidence("Page 1 of 1", "markdown").catch((cause) => cause);
    expect(failure).toBeInstanceOf(EvidenceRefusal);
    expect(failure.category).toBe("empty_evidence");
    expect(failure.message).toContain("no readable content");
  });

  it("turns a dropped connection into a plain error that is not a refusal", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("fetch failed");
      }),
    );
    const failure = await previewEvidence("x", "markdown").catch((cause) => cause);
    expect(failure).not.toBeInstanceOf(EvidenceRefusal);
    expect(failure.message).toContain("never reached the server");
  });
});
