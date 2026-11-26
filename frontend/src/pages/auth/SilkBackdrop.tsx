import { useEffect, useRef } from 'react';

const VERTEX = `
attribute vec2 a_position;
void main() { gl_Position = vec4(a_position, 0.0, 1.0); }
`;

// Original procedural fabric: warped folds, a grazing light and a soft satin sheen.
const FRAGMENT = `
precision highp float;
uniform vec2 u_resolution;
uniform float u_time;

float hash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}
float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  vec2 s = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), s.x),
             mix(hash(i + vec2(0.0, 1.0)), hash(i + 1.0), s.x), s.y);
}
float fbm(vec2 p) {
  float v = 0.0, weight = 0.5;
  for (int i = 0; i < 4; i++) {
    v += weight * noise(p);
    p = mat2(0.8, -0.6, 0.6, 0.8) * p * 2.05 + 4.1;
    weight *= 0.5;
  }
  return v;
}
float fabric(vec2 p, float time) {
  float warp = fbm(p * 0.7 + vec2(time * 0.06, -time * 0.04));
  float fold = p.x * 3.6 + sin(p.y * 1.4 + time * 0.3) * 0.9
    + sin(p.y * 2.3 - time * 0.18) * 0.35 + warp * 2.1;
  return sin(fold) * 0.7 + sin(fold * 2.0 + 0.7) * 0.12;
}
void main() {
  vec2 uv = gl_FragCoord.xy / u_resolution;
  vec2 p = (uv - 0.5) * vec2(u_resolution.x / u_resolution.y, 1.0);
  p = mat2(0.86, -0.51, 0.51, 0.86) * p * 4.5;
  float time = u_time * 0.45;
  float h = fabric(p, time);
  float dx = (fabric(p + vec2(0.015, 0.0), time) - h) / 0.015;
  float dy = (fabric(p + vec2(0.0, 0.015), time) - h) / 0.015;
  vec3 normal = normalize(vec3(-dx * 0.55, -dy * 0.55, 1.0));
  vec3 light = normalize(vec3(-0.5, 0.8, 1.2));
  float diffuse = max(dot(normal, light), 0.0);
  float sheen = pow(max(dot(normal, normalize(light + vec3(0.0, 0.0, 1.0))), 0.0), 24.0);
  float shade = 0.035 + 0.35 * pow(diffuse, 1.4) + sheen * 0.42;
  shade *= 0.72 + 0.28 * smoothstep(0.0, 1.0, uv.y);
  shade += (hash(gl_FragCoord.xy) - 0.5) * 0.012;
  gl_FragColor = vec4(vec3(shade), 1.0);
}
`;

export function SilkBackdrop() {
	const canvasRef = useRef<HTMLCanvasElement>(null);
	useEffect(() => {
		const canvas = canvasRef.current!;
		const gl = canvas.getContext('webgl', { alpha: false, antialias: false, depth: false, powerPreference: 'low-power' });
		// WebGL can be disabled by the browser; the panel's CSS supplies a still backdrop.
		if (!gl) return;
		const shaders = [gl.createShader(gl.VERTEX_SHADER)!, gl.createShader(gl.FRAGMENT_SHADER)!];
		shaders.forEach((shader, index) => { gl.shaderSource(shader, index === 0 ? VERTEX : FRAGMENT); gl.compileShader(shader); });
		const program = gl.createProgram()!;
		shaders.forEach(shader => gl.attachShader(program, shader));
		gl.linkProgram(program);
		if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
			gl.deleteProgram(program);
			shaders.forEach(shader => gl.deleteShader(shader));
			return;
		}
		gl.useProgram(program);
		const buffer = gl.createBuffer();
		gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
		gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]), gl.STATIC_DRAW);
		const position = gl.getAttribLocation(program, 'a_position');
		gl.enableVertexAttribArray(position);
		gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
		const resolution = gl.getUniformLocation(program, 'u_resolution');
		const time = gl.getUniformLocation(program, 'u_time');
		const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
		let frame = 0;
		let elapsed = 0;
		let lastPaint = 0;
		function paint() {
			gl!.uniform1f(time, elapsed);
			gl!.drawArrays(gl!.TRIANGLES, 0, 6);
		}
		function tick(now: number) {
			if (now - lastPaint >= 1000 / 30) {
				elapsed += Math.min(now - lastPaint, 100) / 1000;
				lastPaint = now;
				paint();
			}
			frame = requestAnimationFrame(tick);
		}
		function sync() {
			cancelAnimationFrame(frame);
			const { width, height } = canvas.getBoundingClientRect();
			const visible = width > 0 && height > 0 && !document.hidden;
			canvas.dataset.motion = visible && !reducedMotion.matches ? 'animated' : 'still';
			if (!visible) return;
			const ratio = Math.min(window.devicePixelRatio || 1, 1.5);
			canvas.width = Math.round(width * ratio);
			canvas.height = Math.round(height * ratio);
			gl!.viewport(0, 0, canvas.width, canvas.height);
			gl!.uniform2f(resolution, canvas.width, canvas.height);
			paint();
			if (!reducedMotion.matches) {
				lastPaint = performance.now();
				frame = requestAnimationFrame(tick);
			}
		}
		canvas.dataset.renderer = 'webgl';
		const observer = new ResizeObserver(sync);
		observer.observe(canvas);
		reducedMotion.addEventListener('change', sync);
		document.addEventListener('visibilitychange', sync);
		sync();
		return () => {
			cancelAnimationFrame(frame);
			observer.disconnect();
			reducedMotion.removeEventListener('change', sync);
			document.removeEventListener('visibilitychange', sync);
			gl.deleteBuffer(buffer);
			gl.deleteProgram(program);
			shaders.forEach(shader => gl.deleteShader(shader));
		};
	}, []);
	return <canvas ref={canvasRef} className="auth-silk" aria-hidden="true" />;
}
