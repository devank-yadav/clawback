import { Suspense } from "react";
import ClawbackApp from "@/components/workspace/clawback-app";
import ShellFallback from "@/components/shell/ShellFallback";

export default function Home() {
  return (
    <Suspense fallback={<ShellFallback />}>
      <ClawbackApp />
    </Suspense>
  );
}
