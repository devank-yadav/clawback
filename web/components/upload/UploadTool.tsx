"use client";

import ToolFrame from "@/components/tools/ToolFrame";
import UploadApp from "./UploadApp";

export default function UploadTool() {
  return (
    <ToolFrame
      href="/upload"
      title="Upload a payment slip"
      lead={() => "The statement that came with the payment (some distributors call it a remittance). Clawback reads every deduction on it, checks the lines add up, then checks each one against the contract."}
    >
      {(account) => <UploadApp account={account.id} distributor={account.distributor.name} />}
    </ToolFrame>
  );
}
