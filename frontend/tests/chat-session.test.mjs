import assert from 'node:assert/strict';
import test from 'node:test';

import './load-api.mjs';
const { sessionApi } = await import('../src/api/session.ts');

test('an empty conversation becomes ready after the SSE replay barrier', async (t) => {
	t.mock.method(globalThis, 'fetch', async (url) => {
		assert.equal(url.pathname, '/api/sessions/session/stream');
		assert.equal(url.searchParams.get('replay_notice'), 'true');
		return new Response(': replay-complete\r\n\r\n', {
			headers: { 'Content-Type': 'text/event-stream' },
		});
	});
	const ready = t.mock.fn();
	const stream = sessionApi.streamEvents('session', 'agent', undefined, undefined, {
		onReady: ready,
	});
	assert.equal((await stream.next()).done, true);
	assert.equal(ready.mock.callCount(), 1);
});
