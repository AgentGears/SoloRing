// Shared API error abstraction (M2 §4.3): one typed ApiError for SoloRing
// envelopes AND network-level failures AND malformed responses. Raw fetch or
// parse exceptions never reach UI code, and unknown errors are never silently
// converted to null (empty state must stay distinct from failure state).

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: Record<string, unknown>;

  constructor(
    code: string,
    message: string,
    status: number,
    details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

export const NETWORK_ERROR_CODE = "NETWORK_ERROR";

/** Coerce any thrown value into an ApiError — never returns null. */
export function asApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  return new ApiError(
    "UNEXPECTED_CLIENT_ERROR",
    "An unexpected application error occurred.",
    0,
  );
}

function networkError(cause: unknown): ApiError {
  return new ApiError(
    NETWORK_ERROR_CODE,
    "Could not reach the SoloRing backend.",
    0,
  );
}

function asDetails(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

/** Parse a SoloRing envelope failure; any non-envelope shape is normalized. */
function envelopeError(status: number, body: unknown): ApiError {
  if (
    body &&
    typeof body === "object" &&
    typeof (body as Record<string, unknown>).error_code === "string"
  ) {
    const env = body as {
      error_code: string;
      message?: unknown;
      details?: unknown;
    };
    return new ApiError(
      env.error_code,
      typeof env.message === "string" ? env.message : env.error_code,
      status,
      asDetails(env.details),
    );
  }
  return new ApiError(
    "NON_ENVELOPE_RESPONSE",
    `Unexpected response (HTTP ${status}).`,
    status,
  );
}

/** Fetch with network-failure normalization. Throws ApiError. */
export async function fetchResponse(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  try {
    return await fetch(url, { cache: "no-store", ...init });
  } catch (cause) {
    throw networkError(cause);
  }
}

export async function responseError(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  return envelopeError(res.status, body);
}

/** JSON endpoints: malformed SUCCESS bodies are also normalized (§4.3). */
export async function fetchJson<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetchResponse(url, init);
  if (!res.ok) {
    throw await responseError(res);
  }
  try {
    return (await res.json()) as T;
  } catch {
    throw new ApiError(
      "NON_ENVELOPE_RESPONSE",
      `Unexpected response (HTTP ${res.status}).`,
      res.status,
    );
  }
}

/** Void endpoints (DELETE): success is exactly HTTP 204, no body parse. */
export async function fetchVoid(url: string, init?: RequestInit): Promise<void> {
  const res = await fetchResponse(url, init);
  if (!res.ok) {
    throw await responseError(res);
  }
  if (res.status !== 204) {
    throw new ApiError(
      "NON_ENVELOPE_RESPONSE",
      `Expected HTTP 204, received HTTP ${res.status}.`,
      res.status,
    );
  }
}
