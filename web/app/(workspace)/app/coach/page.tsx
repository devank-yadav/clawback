import { Suspense } from "react";
import ShellFallback from "@/components/shell/ShellFallback";
import CoachApp from "@/components/tools/CoachApp";

export const metadata = { title: "Deal coach · Clawback" };

export default function Page() {
  return (
    <Suspense fallback={<ShellFallback />}>
      <CoachApp />
    </Suspense>
  );
}
