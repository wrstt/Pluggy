import { proxyJson } from "../../_proxy";

export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxyJson(request, `/api/profiles/${encodeURIComponent(id)}`, { method: "PATCH" });
}

export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxyJson(request, `/api/profiles/${encodeURIComponent(id)}`, { method: "DELETE" });
}

