import { afterEach, expect, it, vi } from "vitest";
import { requestCastChange } from "../src/lib/api";

afterEach(() => vi.unstubAllGlobals());
it("preserves the actual request, base version and retry ID in the request-only endpoint", async () => {
  const body = {
    project: "actual-project",
    character_id: "CHAR-001",
    request: "Keep the face, change the coat.",
    base_version: "actual-base",
    id: "same-retry-id",
  };
  const fetcher = vi
    .fn()
    .mockResolvedValue(
      new Response(JSON.stringify({ ...body, status: "requested" }), {
        status: 201,
      }),
    );
  vi.stubGlobal("fetch", fetcher);
  await requestCastChange("server-token", body);
  expect(fetcher).toHaveBeenCalledWith("/api/cast-change", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Studio-Cast-Token": "server-token",
    },
    body: JSON.stringify(body),
  });
});
it("surfaces a stale design rejection without claiming the revision was applied", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ error: "The character design changed; refresh." }),
          { status: 409 },
        ),
      ),
  );
  await expect(
    requestCastChange("token", {
      project: "fixture",
      character_id: "CHAR-001",
      request: "Change coat.",
      base_version: "old",
      id: "same-id",
    }),
  ).rejects.toThrow("design changed");
});
