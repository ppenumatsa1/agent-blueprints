import type { WorkflowCase } from "../api";
import type { WorkflowStudioProfile } from "../studio-profile";

export function CaseSummaryPanel({
  record,
  profile,
}: {
  record: WorkflowCase;
  profile: WorkflowStudioProfile;
}) {
  const projection = profile.projectPayload(record.payload, record);
  return (
    <section aria-labelledby="case-summary-heading">
      <h3 id="case-summary-heading">Request summary</h3>
      <p>{projection.summary}</p>
      {profile.renderPayload ? profile.renderPayload(projection, record) : (
        projection.fields.length > 0 && (
          <dl className="payload-summary">
            {projection.fields.map((field) => (
              <div key={field.label}>
                <dt>{field.label}</dt>
                <dd>{field.value}</dd>
              </div>
            ))}
          </dl>
        )
      )}
    </section>
  );
}

