import type { Scope } from "./api";

export interface ClientConfig {
  tenantId: string;
  clientId: string;
  scopes: Record<Scope, string>;
}

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function readConfig(environment: ImportMetaEnv): ClientConfig {
  const tenantId = environment.VITE_ENTRA_TENANT_ID ?? "";
  const clientId = environment.VITE_ENTRA_SPA_CLIENT_ID ?? "";
  const apiUri = (environment.VITE_ENTRA_API_APP_ID_URI ?? "").replace(/\/$/, "");
  let resource: URL;
  try {
    resource = new URL(apiUri);
  } catch {
    throw new Error("Missing authentication configuration.");
  }
  if (
    !uuid.test(tenantId) ||
    !uuid.test(clientId) ||
    !["api:", "https:"].includes(resource.protocol) ||
    !resource.hostname ||
    resource.username ||
    resource.password ||
    resource.search ||
    resource.hash
  ) {
    throw new Error("Missing authentication configuration.");
  }
  return {
    tenantId,
    clientId,
    scopes: {
      read: `${apiUri}/workflow.read`,
      write: `${apiUri}/workflow.write`,
      approve: `${apiUri}/workflow.approve`,
    },
  };
}
