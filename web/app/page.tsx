import { redirect } from "next/navigation";

// The payment screen (card R1) comes later; for now the review board is the front door.
export default function Home() {
  redirect("/board/demo");
}
