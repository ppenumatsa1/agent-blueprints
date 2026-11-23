import { useEffect, useRef, useState } from "react";

import type { WorkflowActivityItem, WorkflowClient } from "../api";
import type { WorkflowStudioProfile } from "../studio-profile";

const pageSize = 20;

export interface ActivityTimelineProps {
  caseId: string;
  client: WorkflowClient;
  profile: WorkflowStudioProfile;
  refreshKey?: number;
}

export function ActivityTimeline({ caseId, client, profile, refreshKey = 0 }: ActivityTimelineProps) {
  const [items, setItems] = useState<WorkflowActivityItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(false);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [loadedCaseId, setLoadedCaseId] = useState(caseId);
  const generation = useRef(0);
  const stale = loadedCaseId !== caseId;

  useEffect(() => {
    const requestGeneration = ++generation.current;
    let active = true;
    setItems([]);
    setCursor(null);
    setLoading(true);
    setLoadingMore(false);
    setError(false);
    setLoadedCaseId(caseId);
    void client.activity(caseId, { limit: pageSize }).then((page) => {
      if (active && generation.current === requestGeneration) {
        setItems(page.items);
        setCursor(page.next_cursor);
      }
    }).catch(() => {
      if (active && generation.current === requestGeneration) setError(true);
    }).finally(() => {
      if (active && generation.current === requestGeneration) setLoading(false);
    });
    return () => {
      active = false;
    };
  }, [caseId, client, refreshVersion, refreshKey]);

  async function loadMore() {
    if (!cursor || loadingMore) return;
    const requestGeneration = generation.current;
    setLoadingMore(true);
    try {
      const page = await client.activity(caseId, { limit: pageSize, cursor });
      if (generation.current === requestGeneration) {
        setItems((current) => [...current, ...page.items]);
        setCursor(page.next_cursor);
      }
    } catch {
      if (generation.current === requestGeneration) setError(true);
    } finally {
      if (generation.current === requestGeneration) setLoadingMore(false);
    }
  }

  return (
    <section className="activity-timeline" aria-labelledby="activity-heading" aria-busy={loading || loadingMore}>
      <div className="history-heading">
        <h3 id="activity-heading">{profile.history.activityHeading}</h3>
        <button
          type="button"
          className="secondary"
          disabled={loading}
          onClick={() => setRefreshVersion((value) => value + 1)}
        >
          Refresh activity
        </button>
      </div>
      {(loading || stale) && <p role="status">{profile.history.loading}</p>}
      {!loading && !stale && error && <p className="alert" role="alert">{profile.history.error}</p>}
      {!loading && !stale && !error && items.length === 0 && <p>{profile.history.empty}</p>}
      {!loading && !stale && !error && items.length > 0 && (
        <ol className="activity-list" aria-label={profile.history.activityHeading}>
          {items.map((item, index) => (
            <li key={`${item.type}:${item.created_at}:${index}`}>
              <span>{profile.history.events[item.type]}</span>
              <time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString()}</time>
            </li>
          ))}
        </ol>
      )}
      {!loading && !stale && !error && cursor && (
        <button className="secondary" type="button" disabled={loadingMore} onClick={() => void loadMore()}>
          {loadingMore ? profile.history.loading : profile.history.loadMore}
        </button>
      )}
    </section>
  );
}
