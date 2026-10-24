// The fictional people from docs/design.md. Events carry roles, not names, so the screen names them here.
export const CAST = {
  brand: "Peak Bar Co.",
  owner: "Dana",
  controller: "Sam",
  ownerFull: "Dana Okafor",
  controllerFull: "Sam Reyes",
} as const;

/** What the owner's one-tap confirmation sends. It is the recorded reply in fixtures/run-events.json (event "answer"). */
export const OWNER_RULE_REPLY = "accept if notice is at least 14 days";
