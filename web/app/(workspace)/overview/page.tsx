import { Suspense } from "react";
import ClawbackApp from "@/components/workspace/clawback-app";
import ShellFallback from "@/components/shell/ShellFallback";

export const metadata = { title: "Overview · Clawback" };

export default function Page() {
  return (
    <Suspense fallback={<ShellFallback />}>
      <ClawbackApp view="overview" />
    </Suspense>
  );
}
