import { toast } from 'sonner';

import { resolveApiUrl } from './url';
import { authRequestSignal, getCsrfToken, reportUnauthorized } from '@/lib/auth-session';

export const getBaseUrl = () => localStorage.getItem('server_url') ?? '';
export const apiUrl = (path: string, base = getBaseUrl()) => resolveApiUrl(base, path);

export interface ApiScope {
	baseUrl: string;
	authSignal: AbortSignal;
}

/**
 * Structured error thrown for non-2xx HTTP responses.
 * `message` contains the human-readable detail extracted from the backend.
 */
export class ApiError extends Error {
	readonly status: number;
	readonly detail: string;
	readonly code?: string;

	constructor(status: number, detail: string, code?: string) {
		super(detail);
		this.name = 'ApiError';
		this.status = status;
		this.detail = detail;
		this.code = code;
	}
}

export interface ApiRequestOptions extends Partial<ApiScope> {
	/** When true, suppresses the automatic error toast. Useful when the caller shows its own inline error UI. */
	silent?: boolean;
	signal?: AbortSignal;
	/** Gives up after this many ms and reports {@link TIMEOUT_STATUS}. Off by default — a streaming chat is meant to stay open. */
	timeoutMs?: number;
}

interface RequestOptions extends ApiRequestOptions {
	method?: string;
	body?: unknown;
	params?: Record<string, string>;
}

/** Reported when `timeoutMs` elapses. Real 408s come from a server, so either way the request did not complete in time. */
export const TIMEOUT_STATUS = 408;

function buildHeaders(hasBody: boolean, method: string): Record<string, string> {
	const headers: Record<string, string> = {};
	if (hasBody) headers['Content-Type'] = 'application/json';
	// 身份由 Cookie 验证，前端不能通过请求头选择用户。
	if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) headers['X-CSRF-Token'] = getCsrfToken();
	return headers;
}

/** Parse the response body and extract the `detail` field if the backend returned JSON. */
async function extractError(res: Response): Promise<ApiError> {
	const text = await res.text();
	try {
		const detail: unknown = JSON.parse(text)?.detail;
		if (typeof detail === 'string') return new ApiError(res.status, detail);
		if (
			detail &&
			typeof detail === 'object' &&
			'message' in detail &&
			typeof detail.message === 'string'
		) {
			const code =
				'code' in detail && typeof detail.code === 'string' ? detail.code : undefined;
			return new ApiError(res.status, detail.message, code);
		}
		if (detail !== undefined) return new ApiError(res.status, JSON.stringify(detail));
	} catch {
		// not JSON – fall through
	}
	return new ApiError(res.status, text || res.statusText);
}

async function streamRequest(path: string, options: RequestOptions = {}): Promise<Response> {
	const {
		method = 'GET',
		body,
		params,
		signal,
		silent = false,
		baseUrl,
		authSignal,
		timeoutMs,
	} = options;
	const url = apiUrl(path, baseUrl);
	if (params) {
		Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
	}

	// AbortSignal.timeout aborts with a TimeoutError, which is what lets the
	// catch below tell "too slow" apart from the caller's own cancellation.
	const deadline = timeoutMs ? AbortSignal.timeout(timeoutMs) : undefined;
	const combined = AbortSignal.any([
		authRequestSignal(),
		...(authSignal ? [authSignal] : []),
		...(signal ? [signal] : []),
		...(deadline ? [deadline] : []),
	]);

	let res: Response;
	try {
		const form = body instanceof FormData ? body : undefined;
		res = await fetch(url, {
			method,
			headers: buildHeaders(body !== undefined && !form, method),
			credentials: 'include',
			body: form ?? JSON.stringify(body),
			signal: combined,
		});
	} catch (e) {
		// An abort is the caller's own doing — pass it through untouched.
		if (e instanceof DOMException && e.name === 'AbortError') throw e;
		// A server that accepts the connection then stalls would otherwise
		// leave the caller waiting forever.
		const timedOut = e instanceof DOMException && e.name === 'TimeoutError';
		// Otherwise fetch only rejects when the request never reached the
		// server: wrong address, DNS failure, refused connection, blocked
		// preflight. Status 0 distinguishes that from any HTTP-level failure.
		const error = timedOut
			? new ApiError(TIMEOUT_STATUS, 'The server took too long to respond.')
			: new ApiError(
					0,
					'Cannot reach the server. Check the server address and your network.',
				);
		if (!silent) toast.error(error.detail);
		throw error;
	}

	if (!res.ok) {
		const error = await extractError(res);
		if (res.status === 401 && !path.startsWith('/auth/')) reportUnauthorized();
		if (!silent) toast.error(error.detail);
		throw error;
	}

	return res;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
	const res = await streamRequest(path, options);
	if (res.status === 204) return undefined as T;
	return res.json() as Promise<T>;
}

export const client = {
	get: <T>(path: string, params?: Record<string, string>, options?: ApiRequestOptions) =>
		request<T>(path, { method: 'GET', params, ...options }),
	post: <T>(
		path: string,
		body?: unknown,
		params?: Record<string, string>,
		options?: ApiRequestOptions,
	) => request<T>(path, { method: 'POST', body, params, ...options }),
	patch: <T>(
		path: string,
		body?: unknown,
		params?: Record<string, string>,
		options?: ApiRequestOptions,
	) => request<T>(path, { method: 'PATCH', body, params, ...options }),
	delete: <T = void>(
		path: string,
		params?: Record<string, string>,
		options?: ApiRequestOptions,
	) => request<T>(path, { method: 'DELETE', params, ...options }),
	stream: (path: string, options?: RequestOptions) => streamRequest(path, options),
};
