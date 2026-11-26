import { existsSync } from 'node:fs';
import { registerHooks } from 'node:module';
import { fileURLToPath } from 'node:url';

const source = new URL('../src/', import.meta.url);
registerHooks({
	resolve(specifier, context, nextResolve) {
		if (specifier.startsWith('@/')) specifier = new URL(specifier.slice(2), source).href;
		if (specifier.startsWith('file:') || (specifier.startsWith('.') && context.parentURL)) {
			const url = new URL(specifier, context.parentURL);
			if (existsSync(fileURLToPath(new URL(url.href + '.ts')))) specifier = url.href + '.ts';
		}
		return nextResolve(specifier, context);
	},
});

Object.defineProperty(globalThis, 'localStorage', {
	value: { getItem: () => 'https://app.example.test/api' },
	configurable: true,
});
globalThis.window = new EventTarget();
