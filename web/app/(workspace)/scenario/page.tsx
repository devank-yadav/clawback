import { Suspense } from "react";
import ShellFallback from "@/components/shell/ShellFallback";
import ScenarioApp from "@/components/tools/ScenarioApp";

export const metadata = { title: "Try a clause · Clawback" };

export default function Page() {
  return (
    <Suspense fallback={<ShellFallback />}>
      <ScenarioApp />
    </Suspense>
  );
}
