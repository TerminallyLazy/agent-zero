import { test } from "@playwright/test";

test("extension workspace placeholder", async () => {
  test.skip(true, "Requires the unpacked build artifact and Chromium extension launch wiring.");
});
