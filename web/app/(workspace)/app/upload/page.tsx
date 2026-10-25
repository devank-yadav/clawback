import { Suspense } from "react";
import ShellFallback from "@/components/shell/ShellFallback";
import UploadTool from "@/components/upload/UploadTool";

export const metadata = { title: "Bring in a remittance · Clawback" };

export default function Page() {
  return (
    <Suspense fallback={<ShellFallback />}>
      <UploadTool />
    </Suspense>
  );
}
