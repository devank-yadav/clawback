"use client";

import ToolFrame from "@/components/tools/ToolFrame";
import UploadApp from "./UploadApp";

export default function UploadTool() {
  return (
    <ToolFrame
      href="/upload"
      title="Bring in your remittance"
      lead={() => "Drop the statement that came with the payment. Clawback reads every deduction, checks each one against the page, and runs from there."}
    >
      {() => <UploadApp />}
    </ToolFrame>
  );
}
