/** Infrastructure layers: coloured risk dots when seen from far away, glyph markers once zoomed in. */

import type { Layer } from '@deck.gl/core'
import { IconLayer, ScatterplotLayer } from '@deck.gl/layers'
import { ASSET_ORDER, assetsStore, type AssetGroup } from '@/data/assets'
import { assetIconAtlas } from '@/layers/assetIcons'
import { useUi } from '@/state/ui'

/** Above this zoom the markers become glyphs; below it they are small dots so the coast reads as a patch. */
export const MARKER_ZOOM = 7
/** Below this zoom the infrastructure is hidden, so the national view shows weather only. */
export const INFRA_ZOOM = 6

const hover = (group: AssetGroup) => (info: { index: number }) => {
  const i = info.index >= 0 ? group.indices[info.index] : -1
  const cur = useUi.getState().hoverAsset
  if (i !== (cur ?? -1)) useUi.getState().set({ hoverAsset: i >= 0 ? i : null })
}

type BinaryData = { length: number; attributes: Record<string, { value: Float32Array | Uint8Array; size: number }> }
type Cached = { icon: BinaryData; dot: BinaryData; halo: BinaryData }

/** Binary layer data, built once per group so deck.gl sees the same object every frame and never re-uploads. */
const binaryCache = new WeakMap<AssetGroup, Cached>()
function binaryData(g: AssetGroup) {
  let b = binaryCache.get(g)
  if (!b) {
    const getPosition = { value: g.positions, size: 2 }
    const color = { value: g.colors, size: 4 }
    b = {
      icon: { length: g.count, attributes: { getPosition, getColor: color } },
      dot: { length: g.count, attributes: { getPosition, getFillColor: color } },
      halo: { length: g.count, attributes: { getPosition } },
    }
    binaryCache.set(g, b)
  }
  return b
}

/** Small at first sight of the coast so clusters stay readable, growing to a full glyph when zoomed in. */
const markerSize = (zoom: number) => Math.round(Math.min(30, 10 + (zoom - MARKER_ZOOM) * 4))

export function buildAssetLayers(): Layer[] {
  const { data } = assetsStore.getState()
  if (!data) return []
  const { infra, zoom } = useUi.getState()
  if (zoom < INFRA_ZOOM) return []
  const icons = zoom >= MARKER_ZOOM
  const atlas = icons ? assetIconAtlas() : null
  const layers: Layer[] = []
  for (const type of ASSET_ORDER) {
    const g = data.groups.get(type)
    if (!g || !infra[type]) continue
    const binary = binaryData(g)
    if (icons)
      layers.push(
        new ScatterplotLayer({
          id: `assets-halo-${type}`, data: binary.halo, radiusUnits: 'pixels', getRadius: markerSize(zoom) / 2 + 1.5,
          getFillColor: [11, 13, 16, 200], stroked: false, pickable: false, parameters: { depthCompare: 'always' },
        }),
      )
    layers.push(
      icons
        ? new IconLayer({
            id: `assets-icon-${type}`,
            data: binary.icon,
            iconAtlas: atlas!.url,
            iconMapping: atlas!.mapping,
            getIcon: () => type,
            sizeUnits: 'pixels',
            getSize: markerSize(zoom),
            sizeMinPixels: 7,
            pickable: true,
            onHover: hover(g),
            parameters: { depthCompare: 'always' },
          })
        : new ScatterplotLayer({
            id: `assets-dot-${type}`,
            data: binary.dot,
            radiusUnits: 'pixels',
            getRadius: 2.4,
            stroked: false,
            pickable: false,
            parameters: { depthCompare: 'always' },
          }),
    )
  }
  return layers
}
