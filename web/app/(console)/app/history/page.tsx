import { redirect } from "next/navigation";

/** History is now Payments: every payment from every distributor in one list. */
export default function Page() {
  redirect("/app/payments");
}
