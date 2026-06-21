import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

describe("FITorNOT Railway backend config", () => {
  it("forces Dockerfile builds for the Python backend service", () => {
    const configPath = resolve(
      process.cwd(),
      "review-pitfall-checker-v2",
      "railway.json"
    );
    const config = JSON.parse(readFileSync(configPath, "utf8")) as {
      build?: { builder?: string; dockerfilePath?: string };
    };

    expect(config.build?.builder).toBe("DOCKERFILE");
    expect(config.build?.dockerfilePath).toBe(
      "/review-pitfall-checker-v2/Dockerfile"
    );
  });
});
