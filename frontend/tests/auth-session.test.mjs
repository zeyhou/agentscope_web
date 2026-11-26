import assert from 'node:assert/strict';
import test from 'node:test';

import './load-api.mjs';
const { client, ApiError } = await import('../src/api/client.ts');
const { authRequestSignal, resetAuthRequests, setCsrfToken } =
	await import('../src/lib/auth-session.ts');

test('requests preserve the API prefix and send only cookie-derived identity', async (t) => {
	setCsrfToken('csrf');
	t.mock.method(globalThis, 'fetch', async (url, options) => {
		assert.equal(url.href, 'https://app.example.test/api/auth/logout');
		assert.equal(options.credentials, 'include');
		assert.equal(options.headers['X-CSRF-Token'], 'csrf');
		assert.equal(options.headers['X-User-ID'], undefined);
		return new Response(null, { status: 204 });
	});
	await client.post('/auth/logout');
});

test('switching accounts cancels operations captured under the old session', async (t) => {
	const oldSession = authRequestSignal();
	resetAuthRequests();
	t.mock.method(globalThis, 'fetch', async (_url, options) => options.signal.throwIfAborted());
	await assert.rejects(client.get('/agents/', undefined, { authSignal: oldSession }), {
		name: 'AbortError',
	});
});

test('structured backend errors retain their code', async (t) => {
	t.mock.method(globalThis, 'fetch', async () =>
		Response.json(
			{ detail: { code: 'session_not_found', message: 'Missing' } },
			{ status: 404 },
		),
	);
	await assert.rejects(
		client.get('/sessions/', undefined, { silent: true }),
		(error) =>
			error instanceof ApiError &&
			error.code === 'session_not_found' &&
			error.message === 'Missing',
	);
});
