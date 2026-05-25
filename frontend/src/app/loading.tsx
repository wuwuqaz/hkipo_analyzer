import { Loading } from "@/components/Loading";

export default function RootLoading() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-6 py-10 sm:px-10 lg:px-12">
      <Loading message="Loading…" />
    </main>
  );
}
