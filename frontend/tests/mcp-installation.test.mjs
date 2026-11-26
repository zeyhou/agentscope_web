import assert from 'node:assert/strict';
import test from 'node:test';

import './load-api.mjs';
const { hubApi } = await import('../src/api/hub.ts');

test('MCP installation uses the chosen source and sends configuration as JSON', async (t) => {
	const body = { name: 'Demo MCP', values: { endpoint: 'https://example.test/mcp' } };
	t.mock.method(globalThis, 'fetch', async (url, options) => {
		assert.equal(options.method, 'POST');
		assert.equal(url.pathname, '/api/hub/mcp/official/cards/demo/install');
		assert.equal(options.headers['Content-Type'], 'application/json');
		assert.deepEqual(JSON.parse(options.body), body);
		return Response.json({ id: 'installed-mcp' });
	});
	assert.equal((await hubApi.mcp.install('official', 'demo', body)).id, 'installed-mcp');
});
