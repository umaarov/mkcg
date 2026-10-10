export type User = { token: string; username: string; name: string; role: string };

export function getUser(): User | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem("cg_user");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
export function setUser(u: User | null) {
  if (u) localStorage.setItem("cg_user", JSON.stringify(u));
  else localStorage.removeItem("cg_user");
}
export const token = () => getUser()?.token ?? "";

export class ApiError extends Error {
  status: number;
  constructor(status: number, msg: string) {
    super(msg);
    this.status = status;
  }
}

export async function api<T = any>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as any) };
  const t = token();
  if (t) headers["Authorization"] = `Bearer ${t}`;
  let body = init.body;
  if (init.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.json);
  }
  const r = await fetch(path, { ...init, headers, body });
  if (r.status === 401 && typeof window !== "undefined" && !path.startsWith("/api/auth/login")) {
    setUser(null);
    window.location.href = "/login";
    throw new ApiError(401, "not authenticated");
  }
  if (!r.ok) {
    let msg = r.statusText;
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {}
    throw new ApiError(r.status, msg);
  }
  const ct = r.headers.get("content-type") || "";
  return (ct.includes("json") ? r.json() : r.blob()) as any;
}

export const withToken = (path: string) => `${path}${path.includes("?") ? "&" : "?"}t=${encodeURIComponent(token())}`;

export async function download(path: string, filename: string, method = "GET") {
  const blob = await api<Blob>(path, { method });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
