/** One GPU texture per atlas bitmap per device, shared by the wind and rain layers. */

import type { Device, Texture } from '@luma.gl/core'

const cache = new WeakMap<Device, WeakMap<ImageBitmap, Texture>>()

export function atlasTexture(device: Device, bitmap: ImageBitmap): Texture {
  let perDevice = cache.get(device)
  if (!perDevice) cache.set(device, (perDevice = new WeakMap()))
  let tex = perDevice.get(bitmap)
  if (!tex) {
    const { width, height } = bitmap
    tex = device.createTexture({
      width,
      height,
      format: 'rgba8unorm',
      mipLevels: 1,
      sampler: { minFilter: 'linear', magFilter: 'linear', addressModeU: 'clamp-to-edge', addressModeV: 'clamp-to-edge' },
    })
    tex.copyExternalImage({ image: bitmap, width, height, premultipliedAlpha: false })
    perDevice.set(bitmap, tex)
  }
  return tex
}

/** GLSL shared by the weather shaders: map a lon/lat to a texture coordinate inside one atlas tile. */
export const TILE_UV_GLSL = /* glsl */ `
vec2 weather_tileUV(vec2 lnglat, vec4 grid, vec2 gridSize, vec4 tile) {
  // grid = (west, north, step, _): cell centres sit on whole multiples of step.
  vec2 px = vec2((lnglat.x - grid.x) / grid.z, (grid.y - lnglat.y) / grid.z) + 0.5;
  px = clamp(px, vec2(0.5), gridSize - 0.5);
  return tile.xy + px / gridSize * tile.zw;
}
`
