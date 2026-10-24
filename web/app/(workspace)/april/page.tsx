import ToolShell from "@/components/tools/ToolShell";
import AprilApp from "@/components/tools/AprilApp";

export const metadata = { title: "Next month · Clawback" };

export default function Page() {
  return (
    <ToolShell title="Next month" lead="April&apos;s fees, decided by the rule the owner saved in March." current="/april">
      <AprilApp />
    </ToolShell>
  );
}
