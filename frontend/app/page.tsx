import AppHeader from "@/components/app/AppHeader";
import ReviewQueue from "@/components/review/ReviewQueue";

// Review queue: customer requests (EXAMPLE) and recipes held for a scientist (LIVE and EXAMPLE) in one list.
export default function ReviewQueuePage() {
  return (
    <main className="mx-auto max-w-7xl px-4 py-5">
      <AppHeader />
      <ReviewQueue />
    </main>
  );
}
