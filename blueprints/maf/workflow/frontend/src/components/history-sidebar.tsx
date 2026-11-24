import { useEffect, useRef, useState } from "react";

import type { WorkflowClient, WorkflowHistoryItem, WorkflowStatus } from "../api";
import type { WorkflowStudioProfile } from "../studio-profile";

const pageSize = 20;
const statuses: Array<WorkflowStatus | "all"> = [
  "all",
  "created",
  "pending",
  "approved",
  "rejected",
  "completed",
  "failed",
];

export interface HistorySidebarProps {
  profile: WorkflowStudioProfile;
  client: WorkflowClient;
  selectedId: string | null;
  refreshKey?: number;
  disabled?: boolean;
  onSelect(id: string): void;
}

function recordLabel(item: WorkflowHistoryItem): string {
  return `${item.status} workflow`;
}

export function HistorySidebar({
  profile,
  client,
  selectedId,
  refreshKey = 0,
  disabled = false,
  onSelect,
}: HistorySidebarProps) {
  const [status, setStatus] = useState<WorkflowStatus | "all">("all");
  const [items, setItems] = useState<WorkflowHistoryItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(false);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [loadedStatus, setLoadedStatus] = useState<WorkflowStatus | "all">("all");
  const generation = useRef(0);
  const stale = loadedStatus !== status;

  useEffect(() => {
    const requestGeneration = ++generation.current;
    let active = true;
    setItems([]);
    setCursor(null);
    setLoading(true);
    setLoadingMore(false);
    setError(false);
    setLoadedStatus(status);
    void client.listHistory({
      ...(status === "all" ? {} : { status }),
      limit: pageSize,
    }).then((page) => {
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
  }, [client, status, refreshVersion, refreshKey]);

  async function loadMore() {
    if (!cursor || loadingMore) return;
    const requestGeneration = generation.current;
    setLoadingMore(true);
    try {
      const page = await client.listHistory({
        ...(status === "all" ? {} : { status }),
        limit: pageSize,
        cursor,
      });
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
    <aside className="card history-sidebar" aria-labelledby="history-heading" aria-busy={loading || loadingMore}>
      <div className="history-heading">
        <h2 id="history-heading">{profile.history.heading}</h2>
        <button
          className="secondary"
          type="button"
          disabled={loading || disabled}
          onClick={() => setRefreshVersion((value) => value + 1)}
        >
          {profile.history.refresh}
        </button>
      </div>
      <label htmlFor="history-status">Filter by status</label>
      <select
        id="history-status"
        value={status}
        disabled={disabled}
        onChange={(event) => setStatus(event.target.value as WorkflowStatus | "all")}
      >
        {statuses.map((value) => (
          <option key={value} value={value}>{value === "all" ? "All statuses" : value}</option>
        ))}
      </select>
      {(loading || stale) && <p role="status">{profile.history.loading}</p>}
      {!loading && !stale && error && <p className="alert" role="alert">{profile.history.error}</p>}
      {!loading && !stale && !error && items.length === 0 && <p>{profile.history.empty}</p>}
      {!loading && !stale && !error && items.length > 0 && (
        <ul className="history-list">
          {items.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className={`history-item${selectedId === item.id ? " selected" : ""}`}
                aria-pressed={selectedId === item.id}
                disabled={disabled}
                onClick={() => onSelect(item.id)}
              >
                <span>{recordLabel(item)}</span>
                <time dateTime={item.updated_at}>{new Date(item.updated_at).toLocaleString()}</time>
                <span className="identifier">{item.id}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {!loading && !stale && !error && cursor && (
        <button className="secondary" type="button" disabled={loadingMore || disabled} onClick={() => void loadMore()}>
          {loadingMore ? profile.history.loading : profile.history.loadMore}
        </button>
      )}
    </aside>
  );
}
