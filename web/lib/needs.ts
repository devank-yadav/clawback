// Where an item on the owner's list ("Next for you", GET /overview needs_you) opens: a dispute's thread (with its
// letter open, one click from sending, when it's ready to send), or the payment, which opens on what needs you.

import { withAccount } from "./accounts";
import type { NeedsYou } from "./types";

export function needsHref(n: NeedsYou): string {
  const { link } = n;
  if (link.page === "dispute" && link.dispute_id) {
    return withAccount("/disputes", n.account_id, {
      id: link.dispute_id, ...(link.run_id ? { run: link.run_id } : {}), ...(n.kind === "dispute_email" ? { send: "1" } : {}),
    });
  }
  return withAccount("/", n.account_id, link.run_id ? { run: link.run_id } : undefined);
}
