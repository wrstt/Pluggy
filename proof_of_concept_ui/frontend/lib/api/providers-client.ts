export async function listProviders() {
  const response = await fetch("/api/providers");
  if (!response.ok) {
    throw new Error("Providers request failed");
  }
  return response.json();
}
