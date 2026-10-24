import ToolShell from "@/components/tools/ToolShell";
import CoachApp from "@/components/tools/CoachApp";

export const metadata = { title: "Deal Coach · Clawback" };

export default function Page() {
  return (
    <ToolShell title="Deal Coach" lead="Redlines for next month&apos;s draft, each tied to what a clause cost." current="/coach">
      <CoachApp />
    </ToolShell>
  );
}
