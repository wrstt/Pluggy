import { proxyJson } from "../../_proxy";

export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { searchParams } = new URL(request.url);
  const deleteFile = searchParams.get("deleteFile") === "1" || searchParams.get("deleteFile") === "true";
  const suffix = deleteFile ? "?delete_file=true" : "";
  return proxyJson(request, `/api/transfers/${encodeURIComponent(id)}${suffix}`, { method: "DELETE" });
}
