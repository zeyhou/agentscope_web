import { client } from './client';

/** The probe is I/O-free on the server, so anything this slow is a stalled backend. */
const HEALTH_TIMEOUT_MS = 10_000;

export const healthApi = {
	/**
	 * 登录前只探测公开认证状态，服务器地址确认后才保存。
	 */
	check: (baseUrl: string) =>
		client.get<{ service: string; authentication: string; registration_open: boolean }>(
			'/auth/health',
			undefined,
			{
				silent: true,
				baseUrl,
				timeoutMs: HEALTH_TIMEOUT_MS,
			},
		),
	ready: (baseUrl: string) =>
		client.get<{ status: 'ready' }>('/auth/ready', undefined, {
			silent: true,
			baseUrl,
			timeoutMs: HEALTH_TIMEOUT_MS,
		}),
};
