import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { apiGet } from "./api";

interface ApiState<T> {
  data?: T;
  error?: string;
  loading: boolean;
}

interface ApiOptions {
  /** Poll the endpoint every N ms (paused automatically when the tab hides). */
  refetchInterval?: number;
}

/**
 * Fetch a GET endpoint, cached by path via TanStack Query. Pass null to render
 * nothing (no request). The path IS the cache key, so revisiting a screen shows
 * cached data instantly (no re-mount flicker) and only refetches once the data
 * goes stale. The return shape is unchanged from the original hand-rolled hook
 * ({ data, error, loading, reload }), so screens need no changes. Pass
 * `{ refetchInterval }` to poll (opt-in; existing callers are unaffected).
 */
export function useApi<T>(
  path: string | null,
  options: ApiOptions = {},
): ApiState<T> & { reload: () => void } {
  const enabled = path !== null;
  const query = useQuery<T, Error>({
    queryKey: ["api", path],
    queryFn: () => apiGet<T>(path as string),
    enabled,
    refetchInterval: options.refetchInterval,
  });

  const reload = useCallback(() => {
    void query.refetch();
  }, [query]);

  return {
    data: query.data,
    error: query.error ? query.error.message : undefined,
    // Only "loading" on a genuine first fetch with no cached data; a disabled
    // query (path === null) or a cache hit is never loading.
    loading: enabled && query.isPending && query.fetchStatus !== "idle",
    reload,
  };
}

/**
 * Returns a function that invalidates cached API data so charts/tables refetch.
 * Call after any data-changing action (upload, merge, delete). With no argument
 * it refreshes everything; pass a path prefix to scope the refresh.
 */
export function useInvalidateApi(): (pathPrefix?: string) => void {
  const client = useQueryClient();
  return useCallback(
    (pathPrefix?: string) => {
      void client.invalidateQueries({
        predicate: (q) => {
          if (q.queryKey[0] !== "api") return false;
          if (!pathPrefix) return true;
          const p = q.queryKey[1];
          return typeof p === "string" && p.startsWith(pathPrefix);
        },
      });
    },
    [client],
  );
}
