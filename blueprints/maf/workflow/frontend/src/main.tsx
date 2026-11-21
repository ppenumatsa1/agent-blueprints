import { PublicClientApplication } from "@azure/msal-browser";
import { MsalProvider } from "@azure/msal-react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { AuthenticatedApplication } from "./authenticated-app";
import { readConfig } from "./config";
import "./styles.css";

async function start() {
  const rootElement = document.getElementById("root");
  if (!rootElement) throw new Error("The application root is missing.");
  const root = createRoot(rootElement);
  try {
    const config = readConfig(import.meta.env);
    const instance = new PublicClientApplication({
      auth: {
        clientId: config.clientId,
        authority: `https://login.microsoftonline.com/${config.tenantId}`,
        redirectUri: window.location.origin,
      },
      cache: { cacheLocation: "sessionStorage" },
    });
    await instance.initialize();
    const redirect = await instance.handleRedirectPromise();
    if (redirect?.account) instance.setActiveAccount(redirect.account);
    root.render(
      <StrictMode>
        <MsalProvider instance={instance}><AuthenticatedApplication config={config} /></MsalProvider>
      </StrictMode>,
    );
  } catch {
    root.render(
      <main className="shell">
        <section className="card">
          <h1>Configuration required</h1>
          <p role="alert">Configure the Entra tenant, SPA client, and API application URI before signing in.</p>
        </section>
      </main>,
    );
  }
}

void start();
