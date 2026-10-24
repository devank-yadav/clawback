"use client";

import { useCallback, useEffect, useState } from "react";

export type Fetched<T> = { data: T | null; error: string | null; loading: boolean; reload: () => void };

/** Runs `load` on mount (and on reload()). Pass null to skip, for example in fixture mode. State changes only happen in promise callbacks. */
export function useFetched<T>(load: (() => Promise<T>) | null): Fetched<T> {
  const [result, setResult] = useState<{ n: number; data: T | null; error: string | null } | null>(null);
  const [n, setN] = useState(0);

  useEffect(() => {
    if (!load) return;
    let cancelled = false;
    load().then(
      (data) => !cancelled && setResult({ n, data, error: null }),
      (e: Error) => !cancelled && setResult({ n, data: null, error: `Can't reach the Clawback API (${e.message}). Start it with make api, or check NEXT_PUBLIC_API_BASE.` }),
    );
    return () => {
      cancelled = true;
    };
  }, [load, n]);

  const reload = useCallback(() => setN((v) => v + 1), []);
  const current = result?.n === n ? result : null;
  return { data: current?.data ?? result?.data ?? null, error: current?.error ?? null, loading: !!load && !current, reload };
}
