import { useCallback, useEffect, useState } from "react";

import { apiGet } from "./api";

interface ApiState<T> {
  data?: T;
  error?: string;
  loading: boolean;
}

/** Fetch a GET endpoint; pass null to render nothing (no request). */
export function useApi<T>(path: string | null): ApiState<T> & { reload: () => void } {
  const [state, setState] = useState<ApiState<T>>({ loading: path !== null });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (path === null) {
      setState({ loading: false });
      return;
    }
    let alive = true;
    setState({ loading: true });
    apiGet<T>(path)
      .then((data) => {
        if (alive) setState({ data, loading: false });
      })
      .catch((err: unknown) => {
        if (alive)
          setState({
            error: err instanceof Error ? err.message : String(err),
            loading: false,
          });
      });
    return () => {
      alive = false;
    };
  }, [path, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { ...state, reload };
}
