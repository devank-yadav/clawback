"use client";

import { useEffect, useState } from "react";
import { fetchChargeDetail } from "./api";
import type { ChargeDetail } from "./types";

/** The evidence behind one charge: GET /charges/{id}?run_id=. Refetched when the charge's decision changes. */
export function useChargeDetail(chargeId: string, runId: string | null | undefined, version = ""): ChargeDetail | null {
  const [fetched, setFetched] = useState<{ key: string; detail: ChargeDetail } | null>(null);
  const key = `${runId}:${chargeId}:${version}`;

  useEffect(() => {
    if (!runId || !chargeId) return;
    let cancelled = false;
    fetchChargeDetail(chargeId, runId).then(
      (detail) => !cancelled && setFetched({ key, detail }),
      () => undefined, // the panel falls back to the finding already in the stream
    );
    return () => {
      cancelled = true;
    };
  }, [chargeId, runId, key]);

  // Keep showing the previous answer for the same charge while a newer one loads.
  return fetched && fetched.key.startsWith(`${runId}:${chargeId}:`) ? fetched.detail : null;
}
