import { Suspense } from "react";
import ReviewBoard from "@/components/board/ReviewBoard";

export async function generateStaticParams() {
  return [{ run: "demo" }];
}

export default function BoardPage({ params }: PageProps<"/board/[run]">) {
  return (
    <Suspense fallback={<div className="min-h-dvh bg-bg" />}>
      {params.then(({ run }) => (
        <ReviewBoard runId={run} />
      ))}
    </Suspense>
  );
}
