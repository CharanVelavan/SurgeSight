import { GoogleMapsOverlay } from '@deck.gl/google-maps'

/**
 * deck.gl 9.4 GoogleMapsOverlay on a vector map adds a positioning OverlayView whose onAdd creates a
 * canvas-backed Deck. When that runs before WebGLOverlayView.onContextRestored, the interleaved path
 * reuses that Deck and never receives Google's GL context, so nothing draws. In interleaved mode the
 * positioning container is not needed, so skip it.
 */
export class SurgeMapsOverlay extends GoogleMapsOverlay {
  _onAddVectorOverlay(): void {
    const self = this as unknown as { props: { interleaved?: boolean } }
    if (self.props.interleaved ?? true) return
    ;(GoogleMapsOverlay.prototype as unknown as { _onAddVectorOverlay: () => void })._onAddVectorOverlay.call(this)
  }
}
