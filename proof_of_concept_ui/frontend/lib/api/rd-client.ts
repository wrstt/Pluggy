export async function sendToRealDebrid(sourceResultId: string) {
  const response = await fetch("/api/rd", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sourceResultId })
  });

  if (!response.ok) {
    throw new Error("RD request failed");
  }

  return response.json();
}
