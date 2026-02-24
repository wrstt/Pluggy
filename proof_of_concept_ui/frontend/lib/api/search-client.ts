export async function searchSources(query: string) {
  const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
  if (!response.ok) {
    throw new Error("Search request failed");
  }
  return response.json();
}
