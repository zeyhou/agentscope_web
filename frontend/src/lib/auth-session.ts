/** 登录 Token 仅由 HttpOnly Cookie 保存；这里只保存当前页面的 CSRF 值。 */
let csrfToken = '';
let requests = new AbortController();
let preferenceScope = '';

export const authRequestSignal = () => requests.signal;
export const getCsrfToken = () => csrfToken;
export const setCsrfToken = (value: string) => { csrfToken = value; };
export const setAuthAccount = (id: string, server: string) => { preferenceScope = `${server}:${id}`; };
export const userPreferenceKey = (key: string) => `${key}:${preferenceScope}`;

export function resetAuthRequests() {
	requests.abort();
	requests = new AbortController();
	csrfToken = '';
	preferenceScope = '';
}

export function reportUnauthorized() {
	window.dispatchEvent(new Event('agentscope:auth-expired'));
}

/** XHR 上传也携带同一 Cookie、CSRF 和身份切换取消信号。 */
export function authenticateUpload(xhr: XMLHttpRequest) {
	xhr.withCredentials = true;
	xhr.setRequestHeader('X-CSRF-Token', csrfToken);
	const signal = requests.signal;
	const abort = () => xhr.abort();
	signal.addEventListener('abort', abort, { once: true });
	return () => signal.removeEventListener('abort', abort);
}
