import { SearchResultsClient } from "@/components/search/SearchResultsClient";

export default async function SearchPage({
  searchParams
}: {
  searchParams: Promise<{ q?: string; r?: string }>;
}) {
  const params = await searchParams;
  const query = (params.q ?? "").trim();
  const runToken = (params.r ?? "").trim();

  return (
    <main className="space-y-4">
      <h1 className="text-2xl font-semibold">Search Results</h1>
      <SearchResultsClient key={`${query}:${runToken}`} query={query} runToken={runToken} />
    </main>
  );
}
