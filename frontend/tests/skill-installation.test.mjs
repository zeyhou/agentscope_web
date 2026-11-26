import assert from 'node:assert/strict';
import test from 'node:test';

import './load-api.mjs';
const { hubApi } = await import('../src/api/hub.ts');

test('skill installation keeps the source and custom library name', async (t) => {
	t.mock.method(globalThis, 'fetch', async (url, options) => {
		assert.equal(options.method, 'POST');
		assert.equal(url.pathname, '/api/hub/skill/tencent/cards/demo/install');
		assert.equal(url.searchParams.get('name'), 'My skill');
		assert.equal(options.body, undefined);
		return Response.json({ id: 'installed-skill' });
	});
	assert.equal((await hubApi.skill.install('tencent', 'demo', 'My skill')).id, 'installed-skill');
});
