import { QueryClient } from "@tanstack/react-query";

/**
 * Single shared query cache for the whole app. Charts and tables read through
 * `useApi`, which is backed by TanStack Query, so a page that has already been
 * visited renders instantly from cache instead of re-fetching and flickering.
 *
 * staleTime keeps data "fresh" for a couple of minutes (no background refetch
 * within that window); gcTime keeps it in memory a while after the last screen
 * unmounts, so navigating away and back is instant. Data-changing actions
 * (upload / merge / delete) call `queryClient.invalidateQueries()` to refresh.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 2 * 60 * 1000, // 2 minutes
      gcTime: 10 * 60 * 1000, // 10 minutes
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});
