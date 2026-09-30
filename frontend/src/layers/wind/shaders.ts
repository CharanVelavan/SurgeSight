import { WIND_RAMP, rampGlsl } from '@/lib/colors'
import { TILE_UV_GLSL } from '../textures'

const HASH = /* glsl */ `
float wind_hash(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}
float wind_lifeLimit(float id, float maxLife) {
  return maxLife * (0.5 + wind_hash(vec2(id * 1.37, 7.13)));
}
`

// ---- simulation (transform feedback) -------------------------------------------------------------------

const simBlock = /* glsl */ `
uniform windSimUniforms {
  vec4 grid;
  vec2 gridSize;
  vec4 tileA;
  vec4 tileB;
  vec4 spawn;
  float mixT;
  float speedFactor;
  float seed;
  float dropRate;
  float maxLife;
} windSim;
`

export type WindSimProps = {
  grid: [number, number, number, number]
  gridSize: [number, number]
  tileA: [number, number, number, number]
  tileB: [number, number, number, number]
  spawn: [number, number, number, number]
  mixT: number
  speedFactor: number
  seed: number
  dropRate: number
  maxLife: number
  windTexA: unknown
  windTexB: unknown
}

export const windSimModule = {
  name: 'windSim',
  vs: simBlock,
  uniformTypes: {
    grid: 'vec4<f32>',
    gridSize: 'vec2<f32>',
    tileA: 'vec4<f32>',
    tileB: 'vec4<f32>',
    spawn: 'vec4<f32>',
    mixT: 'f32',
    speedFactor: 'f32',
    seed: 'f32',
    dropRate: 'f32',
    maxLife: 'f32',
  },
} as const

/** state = (lon, lat, life in steps, speed m/s). One vertex per particle. */
export const simVs = /* glsl */ `#version 300 es
#define SHADER_NAME wind-particle-step
precision highp float;

in vec4 state;
out vec4 nextState;

uniform sampler2D windTexA;
uniform sampler2D windTexB;

${TILE_UV_GLSL}
${HASH}

vec2 wind_at(vec2 lnglat) {
  vec2 a = texture(windTexA, weather_tileUV(lnglat, windSim.grid, windSim.gridSize, windSim.tileA)).rg;
  vec2 b = texture(windTexB, weather_tileUV(lnglat, windSim.grid, windSim.gridSize, windSim.tileB)).rg;
  return mix(a, b, windSim.mixT) * 80.0 - 40.0;
}

void main() {
  float id = float(gl_VertexID);
  vec2 p = state.xy;
  float life = state.z;
  vec2 w = wind_at(p);
  // m/s -> degrees per step; longitude degrees shrink with latitude.
  vec2 np = p + vec2(w.x / max(cos(radians(p.y)), 0.2), w.y) * windSim.speedFactor;

  vec4 s = windSim.spawn;
  bool outside = np.x < s.x || np.y < s.y || np.x > s.z || np.y > s.w;
  bool dropped = wind_hash(vec2(id, windSim.seed)) < windSim.dropRate;
  if (outside || dropped || life > wind_lifeLimit(id, windSim.maxLife)) {
    np = mix(s.xy, s.zw, vec2(wind_hash(vec2(id, windSim.seed + 1.31)), wind_hash(vec2(id + 0.5, windSim.seed + 2.77))));
    nextState = vec4(np, 0.0, length(wind_at(np)));
  } else {
    nextState = vec4(np, life + 1.0, length(w));
  }
  gl_Position = vec4(0.0);
}
`

// ---- drawing: one quad per trail segment, one draw per trail age ----------------------------------------

const drawBlock = /* glsl */ `
uniform windDrawUniforms {
  float age;
  float numAges;
  float width;
  float opacity;
  float maxLife;
  vec4 domain;
} windDraw;
`

export type WindDrawProps = { age: number; numAges: number; width: number; opacity: number; maxLife: number; domain: [number, number, number, number] }

export const windDrawModule = {
  name: 'windDraw',
  vs: drawBlock,
  fs: drawBlock,
  uniformTypes: { age: 'f32', numAges: 'f32', width: 'f32', opacity: 'f32', maxLife: 'f32', domain: 'vec4<f32>' },
} as const

export const drawVs = /* glsl */ `#version 300 es
#define SHADER_NAME wind-particle-draw
precision highp float;

in vec2 corner;   // x: 0 at the older end, 1 at the newer end; y: -1..1 across the line
in vec4 newer;
in vec4 older;

out vec4 vColor;
out float vAcross;

${HASH}
${rampGlsl('wind_color', WIND_RAMP)}

void main() {
  // Same particle on consecutive steps only; a respawn resets life and breaks the segment.
  bool valid = newer.z == older.z + 1.0;

  vec4 c0 = project_position_to_clipspace(vec3(older.xy, 0.0), vec3(0.0), vec3(0.0));
  vec4 c1 = project_position_to_clipspace(vec3(newer.xy, 0.0), vec3(0.0), vec3(0.0));
  vec2 s0 = c0.xy / c0.w * project.viewportSize;
  vec2 s1 = c1.xy / c1.w * project.viewportSize;
  vec2 d = s1 - s0;
  float len = length(d);
  vec2 dir = len > 1e-4 ? d / len : vec2(1.0, 0.0);
  vec2 normal = vec2(-dir.y, dir.x);

  vec4 pos = mix(c0, c1, corner.x);
  // Taper towards the tail of the trail.
  float along = (windDraw.age + 1.0 - corner.x) / windDraw.numAges;
  float width = windDraw.width * mix(1.0, 0.45, along);
  pos.xy += project_pixel_size_to_clipspace(normal * corner.y * (width * 0.5 + 0.5)) * pos.w;

  float id = float(gl_InstanceID);
  float life = newer.z;
  float fadeIn = clamp(life / 6.0, 0.0, 1.0);
  float fadeOut = clamp((wind_lifeLimit(id, windDraw.maxLife) - life) / 10.0, 0.0, 1.0);
  // Soften the edges of the data domain instead of ending on a hard rectangle.
  vec4 dd = vec4(newer.xy - windDraw.domain.xy, windDraw.domain.zw - newer.xy);
  float edge = clamp(min(min(dd.x, dd.y), min(dd.z, dd.w)) / 2.0, 0.0, 1.0);
  float alpha = (1.0 - along) * fadeIn * fadeOut * edge * windDraw.opacity;

  vec4 col = wind_color(newer.w);
  vColor = vec4(col.rgb, alpha * col.a);
  vAcross = corner.y;
  gl_Position = valid && len < 80.0 * project.devicePixelRatio ? pos : vec4(2.0, 2.0, 2.0, 1.0);
}
`

export const drawFs = /* glsl */ `#version 300 es
#define SHADER_NAME wind-particle-draw
precision highp float;

in vec4 vColor;
in float vAcross;
out vec4 fragColor;

void main() {
  float edge = 1.0 - smoothstep(0.6, 1.0, abs(vAcross));
  fragColor = vec4(vColor.rgb, vColor.a * edge * layer.opacity);
}
`
