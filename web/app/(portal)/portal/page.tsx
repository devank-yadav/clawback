import { Suspense } from "react";
import PortalApp from "@/components/portal/PortalApp";

export default function PortalPage() {
  return (
    <Suspense fallback={<div className="portal" />}>
      <PortalApp />
    </Suspense>
  );
}
