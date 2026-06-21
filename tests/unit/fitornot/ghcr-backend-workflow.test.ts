import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

describe("FITorNOT backend image workflow", () => {
  it("publishes the Python backend image from review-pitfall-checker-v2", () => {
    const workflowPath = resolve(
      process.cwd(),
      ".github",
      "workflows",
      "fitornot-backend-image.yaml"
    );

    expect(existsSync(workflowPath)).toBe(true);

    const workflow = readFileSync(workflowPath, "utf8");

    expect(workflow).toContain("ghcr.io/${{ github.repository_owner }}/fitornot-backend");
    expect(workflow).toContain("context: ./review-pitfall-checker-v2");
    expect(workflow).toContain("file: ./review-pitfall-checker-v2/Dockerfile");
  });
});
