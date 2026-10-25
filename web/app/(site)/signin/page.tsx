import { Suspense } from "react";
import SignInPage from "@/components/shell/SignInPage";

export const metadata = { title: "Sign in · Clawback" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <SignInPage />
    </Suspense>
  );
}
