import { expect, test } from "@playwright/test";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
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

test("browser bearer requests reject redirects before reaching another origin", async ({ browser }) => {
  let destinationRequests = 0;
  const destination = createServer((_request, response) => {
    destinationRequests += 1;
    response.writeHead(200, { "access-control-allow-origin": "*" });
    response.end("{}");
  });
  await new Promise<void>((resolve) => destination.listen(0, "127.0.0.1", resolve));
  const destinationPort = (destination.address() as AddressInfo).port;
  const source = createServer((request, response) => {
    if (request.url === "/") {
      response.writeHead(200, { "content-type": "text/html" });
      response.end("<html></html>");
    } else {
      const status = request.url === "/redirect-307" ? 307 : 302;
      response.writeHead(status, { location: `http://127.0.0.1:${destinationPort}/` });
      response.end();
    }
  });
  await new Promise<void>((resolve) => source.listen(0, "127.0.0.1", resolve));
  try {
    const page = await browser.newPage();
    await page.goto(`http://127.0.0.1:${(source.address() as AddressInfo).port}/`);
    for (const path of ["/redirect-302", "/redirect-307"]) {
      const rejected = await page.evaluate(async (url) => {
        try {
          await fetch(url, {
            method: "POST",
            headers: { Authorization: "Bearer synthetic-canary" },
            body: "synthetic",
            redirect: "error",
          });
          return false;
        } catch {
          return true;
        }
      }, path);
      expect(rejected).toBe(true);
    }
    expect(destinationRequests).toBe(0);
    await page.close();
  } finally {
    await Promise.all([
      new Promise<void>((resolve, reject) => source.close((error) => error ? reject(error) : resolve())),
      new Promise<void>((resolve, reject) => destination.close((error) => error ? reject(error) : resolve())),
    ]);
  }
});
