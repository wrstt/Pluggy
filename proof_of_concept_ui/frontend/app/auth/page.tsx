import { AuthGateClient } from "@/components/auth/AuthGateClient";

export default async function AuthPage({
  searchParams
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const params = await searchParams;
  const nextPath = params.next || "/";
  return <AuthGateClient nextPath={nextPath} />;
}
