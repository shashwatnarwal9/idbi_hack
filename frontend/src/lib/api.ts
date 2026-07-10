/**
 * Typed API client, the ONLY way components talk to the backend.
 * Base URL comes from the Vite env (frontend/.env.development); every value
 * rendered in the UI must arrive through these helpers, never from constants.
 */

const BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let detail = res.statusText;
  try {
    const body = (await res.json()) as {
      detail?: string | { errors?: string[] };
    };
    if (typeof body.detail === "string") {
      detail = body.detail;
    } else if (body.detail?.errors?.length) {
      detail = body.detail.errors.join(" ");
    } else if (body.detail) {
      detail = JSON.stringify(body.detail);
    }
  } catch {
    // non-JSON error body; keep the status text
  }
  return new ApiError(res.status, detail);
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`);
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as T;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as T;
}

export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, { method: "POST", body: form });
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as T;
}

export async function apiDelete<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, { method: "DELETE" });
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as T;
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as T;
}

/** POST that returns a file (e.g. a generated PDF) instead of JSON. */
export async function apiPostFile(
  path: string,
): Promise<{ blob: Blob; filename: string }> {
  const res = await fetch(`${BASE_URL}${path}`, { method: "POST" });
  if (!res.ok) throw await parseError(res);
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = /filename="?([^"]+)"?/.exec(disposition);
  return { blob: await res.blob(), filename: match?.[1] ?? "download" };
}

export interface HealthResponse {
  status: string;
}

export function getHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>("/health");
}
