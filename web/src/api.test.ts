import { afterEach, describe, expect, it, vi } from "vitest";

import { createSession, describeTransportFailure, streamUrl } from "./api";

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
