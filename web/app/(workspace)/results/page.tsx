import ToolShell from "@/components/tools/ToolShell";
import ResultsApp from "@/components/tools/ResultsApp";

export const metadata = { title: "Results · Clawback" };

export default function Page() {
  return (
    <ToolShell title="Results" lead="The final numbers, what went to QuickBooks, and the accuracy check." current="/results">
      <ResultsApp />
    </ToolShell>
  );
}
