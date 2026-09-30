/**
 * Live scalar fields (cloud cover, temperature, humidity): a BitmapLayer whose fragment shader reads one
 * channel of two atlas frames, decodes it linearly to physical units, crossfades and applies a ramp.
 * A class is made per field because each field compiles its own ramp into the shader.
 */

import { BitmapLayer, type BitmapLayerProps } from '@deck.gl/layers'
import type { DefaultProps } from '@deck.gl/core'
import type { Device } from '@luma.gl/core'
import type { Model } from '@luma.gl/engine'
import { rampGlsl, type Stop } from '@/lib/colors'
import { atlasTexture } from '../textures'

type Vec4 = [number, number, number, number]

export interface ScalarLayerProps {
  imageA: ImageBitmap | null
  imageB: ImageBitmap | null
  tileA: Vec4
  tileB: Vec4
  mixT: number
  gridSize: [number, number]
}

export interface ScalarSpec {
  /** Unique, used for the shader module and layer class names. */
  name: string
  /** 0 = R, 1 = G, 2 = B of the extra atlas. */
  channel: 0 | 1 | 2
  min: number
  max: number
  ramp: readonly Stop[]
}

export function makeScalarLayer(spec: ScalarSpec) {
  const u = `scalar_${spec.name}`
  const module = {
    name: u,
    fs: /* glsl */ `
uniform ${u}Uniforms {
  vec4 tileA;
  vec4 tileB;
  vec2 gridSize;
  float mixT;
} ${u};
`,
    uniformTypes: { tileA: 'vec4<f32>', tileB: 'vec4<f32>', gridSize: 'vec2<f32>', mixT: 'f32' },
  } as const
  const ch = ['r', 'g', 'b'][spec.channel]
  const fs = /* glsl */ `#version 300 es
#define SHADER_NAME ${u}-fragment
precision highp float;

uniform sampler2D scalarTexA;
uniform sampler2D scalarTexB;

in vec2 vTexCoord;
in vec2 vTexPos;
out vec4 fragColor;

${rampGlsl(`${u}_color`, spec.ramp)}

vec2 ${u}_uv(vec2 uv, vec4 tile) {
  vec2 px = clamp(uv * ${u}.gridSize, vec2(0.5), ${u}.gridSize - 0.5);
  return tile.xy + px / ${u}.gridSize * tile.zw;
}

float ${u}_decode(vec4 texel) {
  return ${spec.min.toFixed(4)} + texel.${ch} * ${(spec.max - spec.min).toFixed(4)};
}

void main(void) {
  float a = ${u}_decode(texture(scalarTexA, ${u}_uv(vTexCoord, ${u}.tileA)));
  float b = ${u}_decode(texture(scalarTexB, ${u}_uv(vTexCoord, ${u}.tileB)));
  vec4 color = ${u}_color(mix(a, b, ${u}.mixT));
  vec2 cells = min(vTexCoord, 1.0 - vTexCoord) * ${u}.gridSize;
  float edge = clamp(min(cells.x, cells.y) / 8.0, 0.0, 1.0);
  fragColor = vec4(color.rgb, color.a * edge * layer.opacity);
}
`
  const defaultProps: DefaultProps<ScalarLayerProps> = {
    imageA: { type: 'object', value: null, compare: true },
    imageB: { type: 'object', value: null, compare: true },
    tileA: { type: 'array', value: [0, 0, 1, 1], compare: true },
    tileB: { type: 'array', value: [0, 0, 1, 1], compare: true },
    mixT: { type: 'number', value: 0 },
    gridSize: { type: 'array', value: [1, 1], compare: true },
  }

  return class ScalarLayer extends BitmapLayer<ScalarLayerProps & BitmapLayerProps> {
    static layerName = `Scalar_${spec.name}`
    static defaultProps = defaultProps as never

    getShaders() {
      const shaders = super.getShaders()
      return { ...shaders, fs, modules: [...shaders.modules, module] }
    }

    draw(): void {
      const { model, coordinateConversion, bounds } = this.state as { model?: Model; coordinateConversion: number; bounds: number[] }
      const { imageA, imageB, tileA, tileB, mixT, gridSize } = this.props
      if (!model || !imageA || !imageB) return
      const device = this.context.device as Device
      model.shaderInputs.setProps({
        bitmap: { bounds, coordinateConversion, desaturate: 0, tintColor: [1, 1, 1], transparentColor: [0, 0, 0, 0] },
        [u]: {
          tileA, tileB, gridSize, mixT,
          scalarTexA: atlasTexture(device, imageA),
          scalarTexB: atlasTexture(device, imageB),
        },
      })
      model.draw(this.context.renderPass!)
    }
  }
}
