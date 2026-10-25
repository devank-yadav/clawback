import Dashboard from "@/components/app/Dashboard";

export const metadata = { title: "Home · Clawback" };

/** `/app`: the supplier's home, starting with the distributors table. A row opens /app/agents for that distributor. */
export default function Page() {
  return <Dashboard />;
}
