import ToolShell from "@/components/tools/ToolShell";
import AuditApp from "@/components/tools/AuditApp";

export const metadata = { title: "Audit log · Clawback" };

export default function Page() {
  return (
    <ToolShell title="Audit log" lead="Every action, who did it, and the hash chain that proves nothing was edited." current="/audit">
      <AuditApp />
    </ToolShell>
  );
}
