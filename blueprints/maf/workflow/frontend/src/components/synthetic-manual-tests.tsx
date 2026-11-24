import { useState } from "react";

import type { SyntheticManualTest } from "../studio-profile";

export function SyntheticManualTests({ tests }: { tests: readonly SyntheticManualTest[] }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState("");

  async function run(test: SyntheticManualTest) {
    setBusy(true);
    setResult("");
    try {
      const value = await test.run();
      if (!value || (value.outcome !== "passed" && value.outcome !== "failed") ||
        typeof value.summary !== "string") {
        throw new Error("Invalid test result");
      }
      setResult(`${value.outcome === "passed" ? "Passed" : "Failed"}: ${value.summary}`);
    } catch {
      setResult("Manual test could not be completed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-label="Synthetic manual tests">
      <h2>Synthetic manual tests</h2>
      <p>Development only. Runs application-supplied synthetic tests on request.</p>
      {tests.map((test, index) => (
        <button key={index} disabled={busy} onClick={() => void run(test)}>{test.label}</button>
      ))}
      {result && <p role="status">{result}</p>}
    </section>
  );
}
