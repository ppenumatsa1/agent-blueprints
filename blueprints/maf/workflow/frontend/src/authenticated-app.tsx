import { InteractionStatus, type AccountInfo } from "@azure/msal-browser";
import { useMsal } from "@azure/msal-react";
import { useState } from "react";

import { HttpWorkflowClient, type Scope } from "./api";
import type { ClientConfig } from "./config";
import { WorkflowWorkspace } from "./workspace";

const accountKey = (account: AccountInfo) =>
  `${account.homeAccountId}:${account.tenantId}:${account.localAccountId}`;

export function AuthenticatedApplication({ config }: { config: ClientConfig }) {
  const { instance, accounts, inProgress } = useMsal();
  const [selected, setSelected] = useState<AccountInfo | null>(null);
  const present = (account: AccountInfo | null) =>
    account ? accounts.find((item) => accountKey(item) === accountKey(account)) ?? null : null;
  const active = present(selected) ?? present(instance.getActiveAccount()) ?? (accounts.length === 1 ? accounts[0] : null);
  const scopes = Object.values(config.scopes);
  const client = new HttpWorkflowClient(async (scope: Scope) => {
    if (!active) throw new Error("An account must be selected.");
    const result = await instance.acquireTokenSilent({ account: active, scopes: [config.scopes[scope]] });
    return result.accessToken;
  });

  if (accounts.length > 1 && !active) {
    return (
      <main className="shell">
        <section className="card">
          <h1>Choose an account</h1>
          {accounts.map((account: AccountInfo) => (
            <button key={accountKey(account)} onClick={() => { instance.setActiveAccount(account); setSelected(account); }}>
              {account.username}
            </button>
          ))}
        </section>
      </main>
    );
  }
  return (
    <WorkflowWorkspace
      key={active ? accountKey(active) : "signed-out"}
      signedIn={Boolean(active)}
      authBusy={inProgress !== InteractionStatus.None}
      signIn={async () => { await instance.loginRedirect({ scopes }); }}
      signOut={async () => { await instance.logoutRedirect({ account: active }); }}
      client={client}
    />
  );
}
