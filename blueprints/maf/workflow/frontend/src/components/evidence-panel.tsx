import type { WorkflowCase } from "../api";
import type { EvidenceProjection } from "../studio-profile";

export function EvidencePanel({ record, project }: {
  record: WorkflowCase;
  project(record: WorkflowCase): EvidenceProjection;
}) {
  let projection: EvidenceProjection;
  try {
    projection = project(record);
    if (!projection || typeof projection.heading !== "string" || !Array.isArray(projection.items) ||
      !projection.items.every((item) => item && typeof item.label === "string" && typeof item.value === "string")) {
      throw new Error("Invalid evidence projection");
    }
  } catch {
    return <p className="alert" role="alert">Evidence could not be displayed.</p>;
  }
  return (
    <section aria-label={projection.heading}>
      <h4>{projection.heading}</h4>
      {projection.items.length === 0 ? <p>No evidence available.</p> : (
        <dl>
          {projection.items.map((item, index) => (
            <div key={index}><dt>{item.label}</dt><dd>{item.value}</dd></div>
          ))}
        </dl>
      )}
    </section>
  );
}
