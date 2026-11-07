export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const TOKEN_KEY = "grok_dev_token";

export type Me = {
  display_name: string;
  roles: string[];
  capabilities: string[];
  auth_method: string;
  production_oidc: boolean;
};

export type Property = {
  id: string;
  name: string;
  address_line1: string;
  city: string;
  region: string;
  postal_code: string;
  timezone: string;
  version: number;
  unit_count: number;
};

export type Unit = {
  id: string;
  label: string;
  version: number;
};

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

export async function api(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  // The hosted gateway forwards this header as the private API's bearer token.
  if (token) headers.set(process.env.NEXT_PUBLIC_HOSTED_DEMO === "true" ? "X-Grok-Authorization" : "Authorization", `Bearer ${token}`);
  return fetch(`${API_BASE}${path}`, { ...init, headers });
}
