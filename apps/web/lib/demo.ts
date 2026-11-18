import { api, setToken } from "./api";

export const demoDestinations: Record<string, string> = {
  property_manager: "/maintenance/review",
  accounting_staff: "/accounting",
  tenant: "/maintenance",
  contractor: "/maintenance/jobs",
  prospect: "/prequalification",
  owner: "/statements",
};

export async function enterDemoRole(role: string): Promise<string> {
  const response = await api("/v1/demo/session", { method: "POST", body: JSON.stringify({ role }), signal: AbortSignal.timeout(15000) });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error?.message || "This view could not be opened.");
  setToken(body.token);
  return demoDestinations[role];
}
