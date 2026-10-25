import { Suspense } from "react";
import ShellFallback from "@/components/shell/ShellFallback";
import ResultsApp from "@/components/tools/ResultsApp";

export const metadata = { title: "Results · Clawback" };

export default function Page() {
  return (
    <Suspense fallback={<ShellFallback />}>
      <ResultsApp />
    </Suspense>
  );
}
