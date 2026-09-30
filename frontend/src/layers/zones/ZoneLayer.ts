/**
 * Alert zones drawn on the GPU: the severity grid is uploaded as a small texture (R byte = severity / 3.5),
 * filtered bilinearly, and the fragment shader fills each level and draws an anti-aliased line wherever the
 * severity crosses a level boundary. The edges stay smooth at every zoom, unlike a pre-rendered image.
 */

import { BitmapLayer } from '@deck.gl/layers'
import { hexToRgb } from '@/lib/colors'

export const SEV_MAX = 3.5
const HEX = ['#E8C547', '#F08A24', '#E5484D']
const FILL_ALPHA = [0.2, 0.3, 0.38]

const vec = (hex: string, a: number) => {
  const [r, g, b] = hexToRgb(hex).map(c => (c / 255).toFixed(4))
  return `vec4(${r}, ${g}, ${b}, ${a.toFixed(3)})`
}

const zoneFs = /* glsl */ `#version 300 es
#define SHADER_NAME zone-layer-fragment
precision highp float;

uniform sampler2D bitmapTexture;
in vec2 vTexCoord;
in vec2 vTexPos;
out vec4 fragColor;

vec4 zone_fill(float level) {
  if (level < 1.0) return vec4(0.0);
  if (level < 2.0) return ${vec(HEX[0], FILL_ALPHA[0])};
  if (level < 3.0) return ${vec(HEX[1], FILL_ALPHA[1])};
  return ${vec(HEX[2], FILL_ALPHA[2])};
}

vec3 zone_edge(float boundary) {
  if (boundary < 1.5) return ${vec(HEX[0], 1.0)}.rgb;
  if (boundary < 2.5) return ${vec(HEX[1], 1.0)}.rgb;
  return ${vec(HEX[2], 1.0)}.rgb;
}

void main(void) {
  float s = texture(bitmapTexture, vTexCoord).r * ${SEV_MAX.toFixed(1)};
  vec4 fill = zone_fill(floor(s));
  float k = floor(s + 0.5);
  float w = max(fwidth(s), 1e-4);
  float line = (k >= 1.0 && k <= 3.0) ? 1.0 - smoothstep(0.6 * w, 1.6 * w, abs(s - k)) : 0.0;
  vec4 col = mix(fill, vec4(zone_edge(k), 0.95), line);
  fragColor = vec4(col.rgb, col.a * layer.opacity);
}
`

export class ZoneLayer extends BitmapLayer {
  static layerName = 'ZoneLayer'

  getShaders() {
    return { ...super.getShaders(), fs: zoneFs }
  }
}

/** Severity grid (row-major from the north-west node) to the texture the layer reads. */
export function encodeSeverity(sev: Float32Array, W: number, H: number): ImageData {
  const img = new ImageData(W, H)
  for (let i = 0; i < W * H; i++) {
    const o = i * 4
    img.data[o] = Math.round(Math.min(1, Math.max(0, sev[i] / SEV_MAX)) * 255)
    img.data[o + 3] = 255
  }
  return img
}
