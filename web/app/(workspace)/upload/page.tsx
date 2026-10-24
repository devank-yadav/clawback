import ToolShell from "@/components/tools/ToolShell";
import UploadApp from "@/components/upload/UploadApp";

export const metadata = { title: "Bring in a remittance · Clawback" };

export default function Page() {
  return (
    <ToolShell
      title="Bring in your remittance"
      lead="Drop the statement that came with the payment. Clawback reads every deduction, checks each one against the page, and runs from there."
      current="/upload"
    >
      <UploadApp />
    </ToolShell>
  );
}
