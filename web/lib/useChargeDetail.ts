"use client";

import { useEffect, useState } from "react";
import { chargeDetail } from "./fixture";
import { fetchChargeDetail } from "./live";
import type { ChargeDetail } from "./types";
import type { DataSource } from "./useRunEvents";

/** The evidence behind one charge: GET /charges/{id} when live, the recorded fixture otherwise. */
export function useChargeDetail(chargeId: string, runId: string | undefined, source: DataSource): ChargeDetail | null {
  const [fetched, setFetched] = useState<{ key: string; detail: ChargeDetail } | null>(null);
  const key = `${runId}:${chargeId}`;

  useEffect(() => {
    if (source !== "live" || !runId || !chargeId) return;
    let cancelled = false;
    fetchChargeDetail(chargeId, runId).then(
      (detail) => !cancelled && setFetched({ key, detail }),
      () => undefined, // the panel falls back to the finding already in the stream
    );
    return () => {
      cancelled = true;
    };
  }, [chargeId, runId, source, key]);

  if (source === "fixture") return chargeDetail(chargeId);
  return fetched?.key === key ? fetched.detail : null;
}
