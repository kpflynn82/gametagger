import { defineConfig } from "@playwright/test";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
const data = mkdtempSync(join(tmpdir(), "gametagger-browser-"));
mkdirSync(join(data, "reports"));
const method = {
  method_id: "synthetic-interface-test",
  version: "ui-test-only-v1",
  cohort: "Illustrative / UI test data",
  case_ids: ["test"],
  evidence_hashes: { test: "synthetic" },
  observation_hashes: { test: "synthetic" },
  taxonomy_hash: "synthetic-test",
  label_origin: "unavailable",
  label_version: "unavailable",
  conditions: { mode: "metadata_only" },
  kind: "illustrative",
  correct: {},
  accepted_primary: { test: false },
  execution_error: { test: false },
};
writeFileSync(
  join(data, "reports", "ui-test.json"),
  JSON.stringify({
    schema_version: "paired-report-v1",
    report_id: "illustrative-ui-test",
    kind: "illustrative",
    baseline: method,
    candidate: { ...method, method_id: "synthetic-candidate" },
    input_hashes: {},
  }),
);

export default defineConfig({
  testDir: "./browser",
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:8000",
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
    reducedMotion: "reduce",
  },
  webServer: {
    command: `cd .. && GAMETAGGER_DATA_DIR='${data}' GAMETAGGER_LOCAL_DEV=1 GAMETAGGER_LOCAL_ROLE=reviewer .venv/bin/uvicorn gametagger.workspace.app:app --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log`,
    url: "http://127.0.0.1:8000/api/capabilities",
    reuseExistingServer: false,
  },
});
