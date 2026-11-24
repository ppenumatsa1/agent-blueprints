import { useEffect, useState } from "react";

import type { StudioProtocolAdapter, StudioProtocolContext } from "./studio-profile";

/**
 * Register an AG-UI Context entry with an application-owned local consumer.
 * The consumer must remove it when the returned cleanup function is called.
 */
export function createAgUiContextAdapter(
  register: (context: StudioProtocolContext) => () => void,
): StudioProtocolAdapter {
  return function AgUiContextAdapter({ context }) {
    const [failed, setFailed] = useState(false);
    useEffect(() => {
      try {
        const unregister = register(context);
        setFailed(false);
        return () => {
          try {
            unregister();
          } catch {
            console.error("AG-UI context could not be removed.");
          }
        };
      } catch {
        setFailed(true);
      }
    }, [context.description, context.value]);
    return failed ? <p role="alert">AG-UI context could not be shared.</p> : null;
  };
}

/** Inject CopilotKit v2's useAgentContext from an explicitly configured provider. */
export function createCopilotKitContextAdapter(
  useAgentContext: (context: StudioProtocolContext) => void,
): StudioProtocolAdapter {
  return function CopilotKitContextAdapter({ context }) {
    useAgentContext(context);
    return null;
  };
}
