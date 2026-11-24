import type { BrowserContextOptions } from "@playwright/test";

type StorageState = Exclude<NonNullable<BrowserContextOptions["storageState"]>, string>;

export function httpsOrigin(value: string): string {
  if (!/^https:\/\/[a-z0-9.-]+(?::[0-9]+)?\/?$/i.test(value)) {
    throw new Error("An explicit HTTPS origin is required.");
  }
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error("An explicit HTTPS origin is required.");
  }
  if (
    url.protocol !== "https:" ||
    !url.hostname ||
    !/^[a-z0-9.-]+$/.test(url.hostname) ||
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.port === "0"
  ) {
    throw new Error("An explicit HTTPS origin is required.");
  }
  return url.origin;
}

export function authorizedOrigin(baseUrl: string, authorized: string): string {
  const origin = httpsOrigin(authorized);
  if (httpsOrigin(baseUrl) !== origin) {
    throw new Error("The live base URL does not match the authorized origin.");
  }
  return origin;
}

export function checkedStorageState(value: unknown, origin: string): StorageState {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Browser storage state must be an object.");
  }
  const state = value as StorageState;
  if (
    !Array.isArray(state.cookies) ||
    state.cookies.length !== 0 ||
    !Array.isArray(state.origins) ||
    state.origins.some((entry) => !entry || httpsOrigin(entry.origin) !== origin)
  ) {
    throw new Error("Browser storage state must be restricted to the authorized HTTPS origin.");
  }
  return state;
}

export function injectSessionStorage({
  origin,
  entries,
}: {
  origin: string;
  entries: Record<string, string>;
}): void {
  if (window.location.origin !== origin) return;
  for (const [key, value] of Object.entries(entries)) {
    window.sessionStorage.setItem(key, value);
  }
}
