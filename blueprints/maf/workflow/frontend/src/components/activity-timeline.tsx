import { useEffect, useRef, useState } from "react";

import { WorkflowClientError, type WorkflowActivityItem, type WorkflowClient } from "../api";
import type { WorkflowStudioProfile } from "../studio-profile";

const pageSize = 20;
const reconcileIntervalMs = 15_000;
const maxSnapshotPages = 50;

class SnapshotLimitError extends Error {}

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
  const [error, setError] = useState<"history" | "limit" | false>(false);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [loadedCaseId, setLoadedCaseId] = useState(caseId);
  const [snapshotComplete, setSnapshotComplete] = useState(false);
  const [visibleCount, setVisibleCount] = useState(pageSize);
  const generation = useRef(0);
  const ready = useRef(false);
  const loadingMoreRef = useRef(false);
  const loadMoreController = useRef<AbortController | null>(null);
  const pageRevision = useRef(0);
  const stale = loadedCaseId !== caseId;

  useEffect(() => {
    const requestGeneration = ++generation.current;
    let active = true;
    const controller = new AbortController();
    loadMoreController.current?.abort();
    loadingMoreRef.current = false;
    setLoadingMore(false);
    ready.current = false;
    setItems([]);
    setCursor(null);
    setSnapshotComplete(false);
    setVisibleCount(pageSize);
    setLoading(true);
    setLoadingMore(false);
    setError(false);
    setLoadedCaseId(caseId);
    void client.activity(caseId, { limit: pageSize, signal: controller.signal }).then((page) => {
      if (active && generation.current === requestGeneration) {
        setItems(page.items);
        setCursor(page.next_cursor);
      }
    }).catch(() => {
      if (active && generation.current === requestGeneration) setError("history");
    }).finally(() => {
      if (active && generation.current === requestGeneration) {
        ready.current = true;
        setLoading(false);
      }
    });
    return () => {
      active = false;
      controller.abort();
      loadMoreController.current?.abort();
    };
  }, [caseId, client, refreshVersion, refreshKey]);

  useEffect(() => {
    if (!profile.capabilities.liveActivity || !client.activityStream) return;
    const controller = new AbortController();
    const requestGeneration = generation.current;
    let scan: AbortController | null = null;
    let pending = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let scanTimer: ReturnType<typeof setTimeout> | undefined;
    let nextScanAt = 0;

    function accessFailure(reason: unknown) {
      if (reason instanceof WorkflowClientError && reason.authorizationFailure) {
        setItems([]);
        setCursor(null);
        setError("history");
        controller.abort();
        scan?.abort();
        return true;
      }
      return false;
    }

    function requestReconcile() {
      if (controller.signal.aborted || !ready.current) return;
      pending = true;
      if (scan || loadingMoreRef.current || scanTimer) return;
      const delay = Math.max(0, nextScanAt - Date.now());
      if (delay) {
        scanTimer = setTimeout(() => {
          scanTimer = undefined;
          requestReconcile();
        }, delay);
        return;
      }
      pending = false;
      void reconcile();
    }

    async function reconcile() {
      if (controller.signal.aborted || !ready.current) return;
      if (scan || loadingMoreRef.current) {
        pending = true;
        return;
      }
      nextScanAt = Date.now() + reconcileIntervalMs;
      scan = new AbortController();
      const currentScan = scan;
      const currentRevision = pageRevision.current;
      const timeout = setTimeout(() => currentScan.abort(), 60_000);
      const items: WorkflowActivityItem[] = [];
      const seen = new Set<string>();
      let next: string | null = null;
      try {
        for (let pageNumber = 0; pageNumber < maxSnapshotPages; pageNumber += 1) {
          const page = await client.activity(caseId, {
            limit: 100,
            ...(next ? { cursor: next } : {}),
            signal: currentScan.signal,
          });
          items.push(...page.items);
          next = page.next_cursor;
          if (!next) {
            if (!controller.signal.aborted && !currentScan.signal.aborted && generation.current === requestGeneration && pageRevision.current === currentRevision) {
              setItems(items);
              setCursor(null);
              setSnapshotComplete(true);
              setError(false);
            } else if (pageRevision.current !== currentRevision) {
              pending = true;
            }
            return;
          }
          if (seen.has(next)) throw new WorkflowClientError("Activity pagination did not advance.");
          seen.add(next);
        }
        throw new SnapshotLimitError();
      } catch (reason) {
        if (!controller.signal.aborted) {
          if (!accessFailure(reason)) {
            setError(reason instanceof SnapshotLimitError || currentScan.signal.aborted ? "limit" : "history");
          }
        }
      } finally {
        clearTimeout(timeout);
        scan = null;
        if (pending && !controller.signal.aborted) {
          requestReconcile();
        }
      }
    }

    function pause(milliseconds: number): Promise<void> {
      return new Promise((resolve) => {
        const finish = () => {
          clearTimeout(timer);
          controller.signal.removeEventListener("abort", finish);
          resolve();
        };
        timer = setTimeout(finish, milliseconds);
        controller.signal.addEventListener("abort", finish, { once: true });
      });
    }

    async function watch() {
      let failures = 0;
      while (failures < 3 && !controller.signal.aborted) {
        let refreshed = false;
        const startedAt = Date.now();
        try {
          await client.activityStream!(caseId, controller.signal, () => {
            refreshed = true;
            requestReconcile();
          });
        } catch (reason) {
          if (controller.signal.aborted || accessFailure(reason)) return;
        }
        if (!controller.signal.aborted) {
          if (refreshed && Date.now() - startedAt >= 20_000) failures = 0;
          else failures += 1;
          requestReconcile();
          await pause(1000 * Math.max(failures, 1));
        }
      }
      while (!controller.signal.aborted) {
        requestReconcile();
        await pause(10_000);
      }
    }
    void watch();
    return () => {
      controller.abort();
      scan?.abort();
      clearTimeout(timer);
      clearTimeout(scanTimer);
    };
  }, [caseId, client, profile.capabilities.liveActivity, refreshVersion, refreshKey]);

  async function loadMore() {
    if (snapshotComplete) {
      setVisibleCount((count) => count + pageSize);
      return;
    }
    if (!cursor || loadingMore) return;
    const requestGeneration = generation.current;
    const controller = new AbortController();
    loadMoreController.current = controller;
    pageRevision.current += 1;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    try {
      const page = await client.activity(caseId, { limit: pageSize, cursor, signal: controller.signal });
      if (generation.current === requestGeneration) {
        setItems((current) => [...current, ...page.items]);
        setCursor(page.next_cursor);
        setVisibleCount((count) => count + pageSize);
      }
    } catch {
      if (generation.current === requestGeneration) setError("history");
    } finally {
      if (loadMoreController.current === controller) {
        loadingMoreRef.current = false;
        loadMoreController.current = null;
      }
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
      {!loading && !stale && error && (
        <p className="alert" role="alert">
          {error === "limit"
            ? "Live activity exceeds the reconciliation limits. Review this case using another authorized method."
            : profile.history.error}
        </p>
      )}
      {!loading && !stale && !error && items.length === 0 && <p>{profile.history.empty}</p>}
      {!loading && !stale && !error && items.length > 0 && (
        <ol className="activity-list" aria-label={profile.history.activityHeading}>
          {items.slice(0, visibleCount).map((item, index) => (
            <li key={`${item.type}:${item.created_at}:${index}`}>
              <span>{profile.history.events[item.type]}</span>
              <time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString()}</time>
            </li>
          ))}
        </ol>
      )}
      {!loading && !stale && !error && (cursor || (snapshotComplete && visibleCount < items.length)) && (
        <button className="secondary" type="button" disabled={loadingMore} onClick={() => void loadMore()}>
          {loadingMore ? profile.history.loading : profile.history.loadMore}
        </button>
      )}
    </section>
  );
}
