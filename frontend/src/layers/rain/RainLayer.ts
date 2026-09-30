/**
 * Rain radar: a BitmapLayer whose fragment shader samples two atlas frames, decodes the log-scaled bytes
 * to mm/h, crossfades them and applies the rain ramp. Frames change by uniforms only; no uploads while
 * playing.
 */

import { BitmapLayer, type BitmapLayerProps } from '@deck.gl/layers'
import type { DefaultProps } from '@deck.gl/core'
import type { Device } from '@luma.gl/core'
import type { Model } from '@luma.gl/engine'
import { RAIN_RAMP, rampGlsl } from '@/lib/colors'
import { RAIN_MAX } from '@/weather/manifest'
import { atlasTexture } from '../textures'

type Vec4 = [number, number, number, number]

export interface RainLayerProps {
  imageA: ImageBitmap | null
  imageB: ImageBitmap | null
  tileA: Vec4
  tileB: Vec4
  mixT: number
  /** 0 = R channel (IMERG), 2 = B channel (GFS forecast). */
  channel: 0 | 2
  gridSize: [number, number]
}

const rainBlock = /* glsl */ `
uniform rainUniforms {
  vec4 tileA;
  vec4 tileB;
  vec2 gridSize;
  float mixT;
  float channel;
} rain;
`

const rainModule = {
  name: 'rain',
  fs: rainBlock,
  uniformTypes: { tileA: 'vec4<f32>', tileB: 'vec4<f32>', gridSize: 'vec2<f32>', mixT: 'f32', channel: 'f32' },
} as const

const rainFs = /* glsl */ `#version 300 es
#define SHADER_NAME rain-layer-fragment
precision highp float;

uniform sampler2D rainTexA;
uniform sampler2D rainTexB;

in vec2 vTexCoord;
in vec2 vTexPos;
out vec4 fragColor;

${rampGlsl('rain_color', RAIN_RAMP, true)}

vec2 rain_atlasUV(vec2 uv, vec4 tile) {
  vec2 px = clamp(uv * rain.gridSize, vec2(0.5), rain.gridSize - 0.5);
  return tile.xy + px / rain.gridSize * tile.zw;
}

float rain_decode(vec4 texel) {
  float b = rain.channel < 1.0 ? texel.r : texel.b;
  return exp(b * ${Math.log1p(RAIN_MAX).toFixed(6)}) - 1.0;
}

void main(void) {
  float a = rain_decode(texture(rainTexA, rain_atlasUV(vTexCoord, rain.tileA)));
  float b = rain_decode(texture(rainTexB, rain_atlasUV(vTexCoord, rain.tileB)));
  vec4 color = rain_color(mix(a, b, rain.mixT));
  // Soften the domain edges (about 2 degrees).
  vec2 cells = min(vTexCoord, 1.0 - vTexCoord) * rain.gridSize;
  float edge = clamp(min(cells.x, cells.y) / 8.0, 0.0, 1.0);
  fragColor = vec4(color.rgb, color.a * edge * layer.opacity);
}
`

const defaultProps: DefaultProps<RainLayerProps> = {
  imageA: { type: 'object', value: null, compare: true },
  imageB: { type: 'object', value: null, compare: true },
  tileA: { type: 'array', value: [0, 0, 1, 1], compare: true },
  tileB: { type: 'array', value: [0, 0, 1, 1], compare: true },
  mixT: { type: 'number', value: 0 },
  channel: 0,
  gridSize: { type: 'array', value: [1, 1], compare: true },
}

export class RainLayer extends BitmapLayer<RainLayerProps & BitmapLayerProps> {
  static layerName = 'RainLayer'
  static defaultProps = defaultProps as never

  getShaders() {
    const shaders = super.getShaders()
    return { ...shaders, fs: rainFs, modules: [...shaders.modules, rainModule] }
  }

  draw(): void {
    const { model, coordinateConversion, bounds } = this.state as { model?: Model; coordinateConversion: number; bounds: number[] }
    const { imageA, imageB, tileA, tileB, mixT, channel, gridSize } = this.props
    if (!model || !imageA || !imageB) return
    const device = this.context.device as Device
    model.shaderInputs.setProps({
      bitmap: { bounds, coordinateConversion, desaturate: 0, tintColor: [1, 1, 1], transparentColor: [0, 0, 0, 0] },
      rain: {
        tileA, tileB, gridSize, mixT, channel,
        rainTexA: atlasTexture(device, imageA),
        rainTexB: atlasTexture(device, imageB),
      },
    })
    model.draw(this.context.renderPass!)
  }
}
