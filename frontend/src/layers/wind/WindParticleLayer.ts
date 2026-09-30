/**
 * GPU wind particles as a deck.gl layer (technique after webgl-wind by V. Agafonkin, ISC).
 *
 * Particle state lives in GPU buffers and is advected by transform feedback. Instead of fading the previous
 * frame (which breaks in a map that redraws itself), each particle keeps its last `trail` positions in a ring
 * of buffers and every trail segment is drawn as a tapered quad. The field is interpolated between two
 * atlas frames in the shader, so time is continuous.
 */

import { Layer, project32, type DefaultProps, type LayerContext, type UpdateParameters } from '@deck.gl/core'
import type { Buffer, Device } from '@luma.gl/core'
import { BufferTransform, Model } from '@luma.gl/engine'
import { atlasTexture } from '../textures'
import { drawFs, drawVs, simVs, windDrawModule, windSimModule, type WindDrawProps, type WindSimProps } from './shaders'

type Vec4 = [number, number, number, number]

export interface WindParticleLayerProps {
  imageA: ImageBitmap | null
  imageB: ImageBitmap | null
  tileA: Vec4
  tileB: Vec4
  mixT: number
  /** Grid: west, north, step and tile size, from the manifest. */
  grid: Vec4
  gridSize: [number, number]
  /** Data domain: west, south, east, north. Particles only live inside it. */
  domain: Vec4
  numParticles: number
  /** Trail length in simulation steps. */
  trail: number
  /** Line width, CSS px. */
  width: number
  /** Screen speed in CSS px per second per m/s of wind. */
  pixelsPerMs: number
  /** Wall clock (ms) driving the fixed-rate simulation. */
  clockMs: number
  /** False freezes the particles in place (reduced motion or paused rendering). */
  animate: boolean
}

const STEP_MS = 1000 / 60
const MAX_LIFE = 180
const DROP_RATE = 0.002

const defaultProps: DefaultProps<WindParticleLayerProps> = {
  imageA: { type: 'object', value: null, compare: true },
  imageB: { type: 'object', value: null, compare: true },
  tileA: { type: 'array', value: [0, 0, 1, 1], compare: true },
  tileB: { type: 'array', value: [0, 0, 1, 1], compare: true },
  mixT: { type: 'number', value: 0 },
  grid: { type: 'array', value: [0, 0, 1, 0], compare: true },
  gridSize: { type: 'array', value: [1, 1], compare: true },
  domain: { type: 'array', value: [-180, -85, 180, 85], compare: true },
  numParticles: { type: 'number', value: 20000 },
  trail: { type: 'number', value: 16 },
  width: { type: 'number', value: 1.5 },
  pixelsPerMs: { type: 'number', value: 5 },
  clockMs: { type: 'number', value: 0 },
  animate: true,
}

interface State {
  model: Model
  transform: BufferTransform
  ring: Buffer[]
  head: number
  lastStepMs: number
  steps: number
  [key: string]: unknown
}

export class WindParticleLayer extends Layer<WindParticleLayerProps> {
  static layerName = 'WindParticleLayer'
  static defaultProps = defaultProps
  declare state: State

  initializeState(context: LayerContext): void {
    const { device } = context
    const model = new Model(device, {
      ...this.getShaders({ vs: drawVs, fs: drawFs, modules: [project32, windDrawModule] }),
      id: `${this.props.id}-draw`,
      bufferLayout: [
        { name: 'corner', format: 'float32x2' },
        { name: 'newer', format: 'float32x4', stepMode: 'instance' },
        { name: 'older', format: 'float32x4', stepMode: 'instance' },
      ],
      attributes: {
        corner: device.createBuffer({ data: new Float32Array([0, -1, 0, 1, 1, -1, 1, 1]) }),
      },
      topology: 'triangle-strip',
      vertexCount: 4,
      isInstanced: true,
      parameters: {
        depthWriteEnabled: false,
        depthCompare: 'always',
        blend: true,
        blendColorSrcFactor: 'src-alpha',
        blendColorDstFactor: 'one-minus-src-alpha',
        blendAlphaSrcFactor: 'one',
        blendAlphaDstFactor: 'one-minus-src-alpha',
      },
    })
    const transform = new BufferTransform(device, {
      id: `${this.props.id}-step`,
      vs: simVs,
      modules: [windSimModule],
      bufferLayout: [{ name: 'state', format: 'float32x4' }],
      outputs: ['nextState'],
      topology: 'point-list',
    })
    this.setState({ model, transform, ring: [], head: 0, lastStepMs: 0, steps: 0 })
  }

  /** deck.gl sets every instanced model's count from this; the layer has no `data`, so report particles. */
  getNumInstances(): number {
    return this.props.numParticles
  }

  updateState(params: UpdateParameters<this>): void {
    super.updateState(params)
    const { props, oldProps } = params
    if (props.numParticles !== oldProps.numParticles || props.trail !== oldProps.trail || !this.state.ring.length) {
      this._allocate()
    }
  }

  finalizeState(context: LayerContext): void {
    super.finalizeState(context)
    this.state.ring.forEach(b => b.destroy())
    this.state.transform?.destroy()
    this.state.model?.destroy()
  }

  private _allocate(): void {
    const device = this.context.device as Device
    const { numParticles: n, trail, domain } = this.props
    this.state.ring.forEach(b => b.destroy())
    // Seed inside the domain with staggered lives; the spawn box moves particles into view within a few frames.
    const seed = new Float32Array(n * 4)
    for (let i = 0; i < n; i++) {
      seed[i * 4] = domain[0] + Math.random() * (domain[2] - domain[0])
      seed[i * 4 + 1] = domain[1] + Math.random() * (domain[3] - domain[1])
      seed[i * 4 + 2] = 0
      seed[i * 4 + 3] = 0
    }
    const ring = Array.from({ length: trail + 1 }, () => device.createBuffer({ data: seed }))
    this.state.model.setInstanceCount(n)
    this.state.transform.model.setVertexCount(n)
    this.setState({ ring, head: 0, steps: 0 })
  }

  /** Visible part of the data domain, where particles are spawned and kept. */
  private _spawnBox(): Vec4 {
    const [w, s, e, n] = this.props.domain
    const vp = this.context.viewport as unknown as { getBounds?: () => number[] }
    const b = vp.getBounds ? vp.getBounds() : [w, s, e, n]
    const box: Vec4 = [Math.max(w, b[0]), Math.max(s, b[1]), Math.min(e, b[2]), Math.min(n, b[3])]
    return box[0] < box[2] && box[1] < box[3] ? box : [w, s, e, n]
  }

  private _step(texA: unknown, texB: unknown): void {
    const { ring, head, transform } = this.state
    const { tileA, tileB, mixT, grid, gridSize, pixelsPerMs } = this.props
    const zoom = (this.context.viewport as unknown as { zoom: number }).zoom
    const pxPerDegree = (512 * 2 ** zoom) / 360
    const next = (head + 1) % ring.length
    const simProps: WindSimProps = {
      grid,
      gridSize,
      tileA,
      tileB,
      spawn: this._spawnBox(),
      mixT,
      speedFactor: (pixelsPerMs * (STEP_MS / 1000)) / pxPerDegree,
      seed: (this.state.steps % 997) + 0.123,
      dropRate: DROP_RATE,
      maxLife: MAX_LIFE,
      windTexA: texA,
      windTexB: texB,
    }
    transform.model.shaderInputs.setProps({ windSim: simProps })
    transform.run({
      inputBuffers: { state: ring[head] },
      outputBuffers: { nextState: ring[next] },
      clearColor: false,
      clearDepth: false,
      clearStencil: false,
    })
    this.state.head = next
    this.state.steps += 1
  }

  draw(): void {
    const { imageA, imageB, animate, clockMs, trail, width, domain } = this.props
    const { model, ring } = this.state
    if (!imageA || !imageB || !ring.length) return
    const device = this.context.device as Device
    const texA = atlasTexture(device, imageA)
    const texB = atlasTexture(device, imageB)

    if (animate) {
      if (!this.state.lastStepMs || clockMs - this.state.lastStepMs > 250) this.state.lastStepMs = clockMs - STEP_MS
      // Fixed-rate simulation: trails keep the same length on 60 Hz and 120 Hz displays.
      let n = 0
      while (clockMs - this.state.lastStepMs >= STEP_MS && n < 3) {
        this._step(texA, texB)
        this.state.lastStepMs += STEP_MS
        n++
      }
    }

    const len = ring.length
    const ages = Math.min(trail, this.state.steps)
    for (let age = 0; age < ages; age++) {
      const newer = ring[(this.state.head - age + len * 2) % len]
      const older = ring[(this.state.head - age - 1 + len * 2) % len]
      model.setAttributes({ newer, older })
      const drawProps: WindDrawProps = { age, numAges: trail, width, opacity: 0.85, maxLife: MAX_LIFE, domain }
      model.shaderInputs.setProps({ windDraw: drawProps })
      model.draw(this.context.renderPass!)
    }
  }
}
