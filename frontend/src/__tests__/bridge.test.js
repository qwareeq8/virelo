import { describe, expect, it } from "vitest";
import { parseSettingsResult } from "../bridge.js";

describe("parseSettingsResult", () => {
  it("Returns settings from a successful backend response.", () => {
    expect(
      parseSettingsResult(
        JSON.stringify({ ok: true, data: { width_pct: 76 } }),
      ),
    ).toEqual({ width_pct: 76 });
  });

  it("Rejects a backend failure instead of returning writeable defaults.", () => {
    expect(() =>
      parseSettingsResult(
        JSON.stringify({ ok: false, error: "Settings read failed." }),
      ),
    ).toThrow("Settings read failed.");
  });

  it("Rejects a successful response without an object payload.", () => {
    expect(() =>
      parseSettingsResult(JSON.stringify({ ok: true, data: null })),
    ).toThrow("The backend did not return settings data.");
  });
});
