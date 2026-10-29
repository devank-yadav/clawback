"use client";

import { useCallback, useEffect, useState } from "react";
import { unreachable } from "./api";

export type Fetched<T> = { data: T | null; error: string | null; loading: boolean; reload: () => void };

/**
 * Runs `load` on mount, on reload(), and whenever `key` changes (a run moved on, so its numbers may have too).
 * Pass null to skip until its inputs are known. The previous data stays on screen while a reload runs.
 * State changes only happen in promise callbacks.
 */
export function useFetched<T>(load: (() => Promise<T>) | null, key = ""): Fetched<T> {
  const [result, setResult] = useState<{ n: number; data: T | null; error: string | null; load?: unknown; key?: string } | null>(null);
  const [n, setN] = useState(0);

  useEffect(() => {
    if (!load) return;
    let cancelled = false;
    load().then(
      (data) => !cancelled && setResult({ n, data, error: null, load, key }),
      // A failed reload of the same thing keeps what was on screen (and anything typed into it); the error is
      // still reported. A failed load of something else shows nothing old.
      (e: Error) => !cancelled && setResult((prev) => ({ n, data: prev && prev.load === load && prev.key === key ? prev.data : null, error: unreachable(e), load, key })),
    );
    return () => {
      cancelled = true;
    };
  }, [load, n, key]);

  const reload = useCallback(() => setN((v) => v + 1), []);
  const current = result?.n === n ? result : null;
  return { data: current?.data ?? result?.data ?? null, error: current?.error ?? null, loading: !!load && !current, reload };
}
