import { Suspense } from "react";
import ShellFallback from "@/components/shell/ShellFallback";
import AprilApp from "@/components/tools/AprilApp";

export const metadata = { title: "Next month · Clawback" };

export default function Page() {
  return (
    <Suspense fallback={<ShellFallback />}>
      <AprilApp />
    </Suspense>
  );
}
