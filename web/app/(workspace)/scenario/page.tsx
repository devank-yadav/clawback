import ToolShell from "@/components/tools/ToolShell";
import ScenarioApp from "@/components/tools/ScenarioApp";

export const metadata = { title: "Try your own clause · Clawback" };

export default function Page() {
  return (
    <ToolShell title="Try your own clause" lead="Paste a clause and a charge. Clawback decides it and shows its evidence." current="/scenario">
      <ScenarioApp />
    </ToolShell>
  );
}
