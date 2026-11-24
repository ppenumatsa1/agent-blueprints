import { expect, test } from "@playwright/test";
import { authorizedOrigin, checkedStorageState, injectSessionStorage } from "./live-origin";

const origin = "https://app.example.test";

test("live authorization rejects unsafe and mismatched origins and browser state", () => {
  for (const value of [
    "",
    "http://app.example.test",
    "https://app.example.test/path",
    "https://app.example.test?query",
    "https://app.example.test#fragment",
    "https://app.example.test@attacker.example",
    "https://app.example.test\\@attacker.example",
    "https://app.example.test:",
    "https://app.example.test:0",
  ]) {
    expect(() => authorizedOrigin(value, origin)).toThrow();
  }
  expect(authorizedOrigin("HTTPS://APP.EXAMPLE.TEST:443/", origin)).toBe(origin);
  expect(() => authorizedOrigin("https://attacker.example", origin)).toThrow();
  expect(checkedStorageState({ cookies: [], origins: [] }, origin)).toEqual({
    cookies: [],
    origins: [],
  });
  expect(() =>
    checkedStorageState(
      { cookies: [], origins: [{ origin: "https://attacker.example", localStorage: [] }] },
      origin,
    ),
  ).toThrow();
  for (const cookie of [
    { domain: ".example.test", secure: true },
    { domain: "attacker.example", secure: true },
    { domain: "app.example.test", secure: false },
    { domain: "app.example.test", secure: true },
  ]) {
    expect(() => checkedStorageState({ cookies: [cookie], origins: [] }, origin)).toThrow();
  }
});

test("session storage is injected only into the authorized origin", async ({ browser }) => {
  const context = await browser.newContext();
  try {
    await context.route("**/*", (route) =>
      route.fulfill({ contentType: "text/html", body: "<html></html>" }),
    );
    await context.addInitScript(injectSessionStorage, {
      origin,
      entries: { "synthetic-canary": "synthetic-value" },
    });
    const page = await context.newPage();
    await page.goto(`${origin}/`);
    expect(await page.evaluate(() => sessionStorage.getItem("synthetic-canary"))).toBe(
      "synthetic-value",
    );
    await page.evaluate(() => {
      const frame = document.createElement("iframe");
      frame.src = "https://attacker.example/";
      document.body.append(frame);
    });
    await expect.poll(() => page.frames().some((frame) => frame.url() === "https://attacker.example/")).toBe(true);
    const attackerFrame = page.frames().find((frame) => frame.url() === "https://attacker.example/")!;
    expect(await attackerFrame.evaluate(() => sessionStorage.getItem("synthetic-canary"))).toBeNull();
    await page.goto("https://attacker.example/");
    expect(await page.evaluate(() => sessionStorage.getItem("synthetic-canary"))).toBeNull();
    await page.goto("http://app.example.test/");
    expect(await page.evaluate(() => sessionStorage.getItem("synthetic-canary"))).toBeNull();
  } finally {
    await context.close();
  }
});
