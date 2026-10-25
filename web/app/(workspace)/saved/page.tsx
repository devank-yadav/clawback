import { Suspense } from "react";
import RecordsApp from "@/components/tools/RecordsApp";
import ShellFallback from "@/components/shell/ShellFallback";

export const metadata = { title: "Records · Clawback" };

export default function Page() {
  return (
    <Suspense fallback={<ShellFallback />}>
      <RecordsApp />
    </Suspense>
  );
}
