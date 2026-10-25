import { Suspense } from "react";
import ClawbackApp from "@/components/workspace/clawback-app";
import ShellFallback from "@/components/shell/ShellFallback";

export const metadata = { title: "Charges · Clawback" };

export default function Page() {
  return (
    <Suspense fallback={<ShellFallback />}>
      <ClawbackApp view="payments" />
    </Suspense>
  );
}
