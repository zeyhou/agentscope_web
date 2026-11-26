import { createRequire } from 'node:module';
import path from 'path';

import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig, normalizePath } from 'vite';
import { viteStaticCopy } from 'vite-plugin-static-copy';
import svgr from 'vite-plugin-svgr';

const require = createRequire(import.meta.url);
const vadEntry = require.resolve('@ricky0123/vad-web');
const vadDir = path.dirname(vadEntry);
const onnxDir = path.dirname(createRequire(vadEntry).resolve('onnxruntime-web'));
const flattenAsset = { stripBase: true } as const;
const frontendPort = 5173;

export default defineConfig({
	plugins: [
		react(),
		tailwindcss(),
		svgr(),
		viteStaticCopy({
			targets: [
				...['cmaps', 'standard_fonts', 'wasm', 'iccs'].map((folder) => ({
					src: normalizePath(
						path.resolve(__dirname, `node_modules/pdfjs-dist/${folder}/*`),
					),
					dest: `pdfjs/${folder}`,
					rename: flattenAsset,
				})),
				{
					src: normalizePath(path.join(vadDir, 'vad.worklet.bundle.min.js')),
					dest: 'voice',
					rename: flattenAsset,
				},
				{
					src: normalizePath(path.join(vadDir, 'silero_vad_v5.onnx')),
					dest: 'voice',
					rename: flattenAsset,
				},
				{
					src: normalizePath(path.join(onnxDir, 'ort-wasm-simd-threaded.{mjs,wasm}')),
					dest: 'voice',
					rename: flattenAsset,
				},
			],
		}),
	],
	server: {
		port: frontendPort,
		strictPort: true,
		proxy: {
			'^/api(?=/|$)': {
				target: 'http://127.0.0.1:8088',
				ws: true,
				rewrite: (url) => url.replace(/^\/api(?=\/|$)/, '') || '/',
			},
		},
	},
	preview: { port: frontendPort, strictPort: true },
	resolve: {
		alias: {
			'@': path.resolve(__dirname, './src'),
			'next/navigation': path.resolve(__dirname, './src/lib/next-navigation-shim.ts'),
		},
	},
	optimizeDeps: {
		include: ['pdfjs-dist'],
	},
});
