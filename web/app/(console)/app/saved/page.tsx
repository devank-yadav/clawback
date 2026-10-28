import { redirect } from "next/navigation";

// Saved became Rules: the rules live at /app/rules, the contracts on the Contracts page.
export default function Page() {
  redirect("/app/rules");
}
