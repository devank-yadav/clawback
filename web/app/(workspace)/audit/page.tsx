import { Suspense } from "react";
import ShellFallback from "@/components/shell/ShellFallback";
import AuditApp from "@/components/tools/AuditApp";

export const metadata = { title: "Audit log · Clawback" };

export default function Page() {
  return (
    <Suspense fallback={<ShellFallback />}>
      <AuditApp />
    </Suspense>
  );
}
