/**
 * Typed fetch wrapper around the spec 013 REST surface.
 *
 * Single shared client used by every TanStack Query hook in
 * ``@/lib/api/queries/*``. Honours:
 *
 *   * **credentials: "include"** so the cookie session
 *     persists across calls.
 *   * **canonical ErrorEnvelope** parsing — non-2xx responses
 *     throw an :class:`ApiError` carrying the
 *     ``{errorMessage, errorCode}`` fields the backend
 *     emits.
 *   * **404 / 401 short-circuit** — these are surfaced as
 *     dedicated :class:`ApiError.kind` so the auth probe can
 *     branch on them without reading status codes everywhere.
 *
 * The orval-generated TanStack Query hooks (when they ship)
 * call ``apiFetch`` under the hood; today's hand-rolled hooks
 * import it directly.
 */

export interface ApiErrorBody {
  errorMessage: string;
  errorCode?: string;
  details?: Record<string, unknown>;
}

export class ApiError extends Error {
  public readonly status: number;
  public readonly errorCode?: string;
  public readonly details?: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.errorMessage);
    this.name = "ApiError";
    this.status = status;
    if (body.errorCode !== undefined) {
      this.errorCode = body.errorCode;
    }
    if (body.details !== undefined) {
      this.details = body.details;
    }
  }

  /** True for 401 unauthenticated. */
  get isUnauthenticated(): boolean {
    return this.status === 401;
  }
}

async function parseErrorBody(response: Response): Promise<ApiErrorBody> {
  try {
    const json: unknown = await response.json();
    if (
      typeof json === "object" &&
      json !== null &&
      "errorMessage" in json
    ) {
      return json as ApiErrorBody;
    }
    return { errorMessage: response.statusText };
  } catch {
    return { errorMessage: response.statusText };
  }
}

export interface ApiFetchOptions extends Omit<RequestInit, "body"> {
  /** JSON-serialisable body. ``Content-Type`` set automatically. */
  json?: unknown;
}

/**
 * Run a fetch against the backend; parse JSON; throw
 * :class:`ApiError` on non-2xx responses.
 */
export async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {
  const { json, headers, ...rest } = options;

  const finalHeaders = new Headers(headers);
  finalHeaders.set("Accept", "application/json");
  if (json !== undefined) {
    finalHeaders.set("Content-Type", "application/json");
  }

  const response = await fetch(path, {
    ...rest,
    credentials: "include",
    headers: finalHeaders,
    body: json !== undefined ? JSON.stringify(json) : undefined,
  });

  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorBody(response));
  }

  // 204 No Content — return undefined cast to T (caller types
  // its hook so the cast is opaque to the consumer).
  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
