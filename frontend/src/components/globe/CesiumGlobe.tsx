import React, { useEffect, useRef } from 'react'
import {
  Cartesian2,
  Cartesian3,
  Color,
  HeadingPitchRange,
  Ion,
  JulianDate,
  LabelStyle,
  Matrix3,
  OpenStreetMapImageryProvider,
  PolylineGlowMaterialProperty,
  Transforms,
  VerticalOrigin,
  Viewer,
} from 'cesium'
import 'cesium/Build/Cesium/Widgets/widgets.css'
import type {
  PropagatedOrbitStateResponse,
  TrajectoryPointResponse,
} from '../../types/api'

/**
 * Convert a TEME position (from SGP4) to the Cesium pseudo-fixed
 * Earth-fixed frame used for rendering on the globe.
 *
 * Cesium's computeTemeToPseudoFixedMatrix() provides the TEME to
 * pseudo-fixed transformation and treats UT1 as equivalent to UTC.
 * This is appropriate for visualization but is not presented as
 * high-precision astrodynamic positioning.
 *
 * @param xKm TEME position X in km
 * @param yKm TEME position Y in km
 * @param zKm TEME position Z in km
 * @param utcIso UTC timestamp as ISO-8601 string
 * @returns Cartesian3 in Cesium's pseudo-fixed frame, in meters
 */
export function temeToFixedFrame(
  xKm: number,
  yKm: number,
  zKm: number,
  utcIso: string,
): Cartesian3 {
  const julianDate = JulianDate.fromIso8601(utcIso)
  const rotMatrix = Transforms.computeTemeToPseudoFixedMatrix(julianDate)
  // Cesium positions are expressed in meters; SGP4 returns km
  const temeMeters = new Cartesian3(xKm * 1000, yKm * 1000, zKm * 1000)
  return Matrix3.multiplyByVector(rotMatrix, temeMeters, new Cartesian3())
}

interface CesiumGlobeProps {
  satelliteState: PropagatedOrbitStateResponse | null
  trajectoryPoints: TrajectoryPointResponse[] | null
  onFlyToReady?: (flyToFn: () => void) => void
}

export default function CesiumGlobe({
  satelliteState,
  trajectoryPoints,
  onFlyToReady,
}: CesiumGlobeProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const viewerRef = useRef<Viewer | null>(null)

  // Initialize Cesium Viewer
  useEffect(() => {
    if (!containerRef.current || viewerRef.current) return

    const ionToken = import.meta.env.VITE_CESIUM_ION_TOKEN

    if (ionToken) {
      Ion.defaultAccessToken = ionToken
    }

    // Create Viewer with baseLayer: false so CesiumWidget does not attempt to
    // load any default imagery (which would silently fall back to Cesium ion).
    // We add our own imagery provider explicitly after creation.
    const viewer = new Viewer(containerRef.current, {
      baseLayer: false,          // prevents any auto imagery load
      animation: false,
      timeline: false,
      infoBox: false,
      selectionIndicator: false,
      navigationHelpButton: false,
      sceneModePicker: false,
      geocoder: false,
      homeButton: true,
      baseLayerPicker: false,
      terrainProvider: undefined,
    })

    viewerRef.current = viewer

    // Add imagery after Viewer is fully constructed
    if (ionToken) {
      // Token provided: use Cesium ion World Imagery (Bing Maps)
      import('cesium').then(({ IonImageryProvider }) => {
        if (!viewer.isDestroyed()) {
          // IonImageryProvider.fromAssetId returns a Promise in Cesium 1.105+
          void IonImageryProvider.fromAssetId(2).then((provider) => {
            if (!viewer.isDestroyed()) {
              viewer.imageryLayers.addImageryProvider(provider)
            }
          })
        }
      })
    } else {
      // Tokenless path: OpenStreetMap tiles — zero ion calls required.
      // OpenStreetMapImageryProvider is Cesium's dedicated OSM provider.
      const osmProvider = new OpenStreetMapImageryProvider({
        url: 'https://tile.openstreetmap.org/',
        credit: '© OpenStreetMap contributors',
        maximumLevel: 19,
      })
      viewer.imageryLayers.addImageryProvider(osmProvider)
    }

    // Expose flyTo function to parent via callback
    const flyToSatellite = () => {
      if (!viewer || viewer.isDestroyed()) return
      const entity = viewer.entities.getById('satellite-point')
      if (entity) {
        viewer.flyTo(entity, {
          duration: 1.5,
          offset: new HeadingPitchRange(0.0, -Math.PI / 4, 3000000),
        })
      }
    }

    if (onFlyToReady) {
      onFlyToReady(flyToSatellite)
    }

    return () => {
      if (viewerRef.current && !viewerRef.current.isDestroyed()) {
        viewerRef.current.destroy()
        viewerRef.current = null
      }
    }
  }, [onFlyToReady])

  // Update satellite point entity when orbitState changes
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer || viewer.isDestroyed()) return

    const existingPoint = viewer.entities.getById('satellite-point')
    if (existingPoint) {
      viewer.entities.remove(existingPoint)
    }

    if (!satelliteState) return

    try {
      const fixedPos = temeToFixedFrame(
        satelliteState.position_x_km,
        satelliteState.position_y_km,
        satelliteState.position_z_km,
        satelliteState.timestamp,
      )

      const entity = viewer.entities.add({
        id: 'satellite-point',
        name: `${satelliteState.object_name} (${satelliteState.norad_cat_id})`,
        position: fixedPos,
        point: {
          pixelSize: 10,
          color: Color.fromCssColorString('#22d3ee'), // cyan-400
          outlineColor: Color.WHITE,
          outlineWidth: 2,
        },
        label: {
          text: `${satelliteState.object_name} [${satelliteState.norad_cat_id}]`,
          font: '12px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
          fillColor: Color.WHITE,
          outlineColor: Color.BLACK,
          outlineWidth: 2,
          style: LabelStyle.FILL_AND_OUTLINE,
          verticalOrigin: VerticalOrigin.BOTTOM,
          pixelOffset: new Cartesian2(0, -14),
        },
      })

      // Fly camera to satellite after placement
      viewer.flyTo(entity, {
        duration: 2.0,
        offset: new HeadingPitchRange(0.0, -Math.PI / 4, 4000000),
      })
    } catch (err) {
      console.error('Error positioning satellite on globe:', err)
    }
  }, [satelliteState])

  // Update trajectory polyline entity when trajectory changes
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer || viewer.isDestroyed()) return

    const existingTraj = viewer.entities.getById('satellite-trajectory')
    if (existingTraj) {
      viewer.entities.remove(existingTraj)
    }

    if (!trajectoryPoints || trajectoryPoints.length === 0) return

    try {
      // Skip points with SGP4 errors — leave gaps rather than plot bad data
      const validPoints = trajectoryPoints.filter((pt) => pt.sgp4_error === 0)
      if (validPoints.length < 2) return

      const positions: Cartesian3[] = validPoints.map((pt) =>
        temeToFixedFrame(
          pt.position_x_km,
          pt.position_y_km,
          pt.position_z_km,
          pt.timestamp,
        ),
      )

      viewer.entities.add({
        id: 'satellite-trajectory',
        name: 'Orbital Trajectory Arc',
        polyline: {
          positions: positions,
          width: 3.0,
          material: new PolylineGlowMaterialProperty({
            glowPower: 0.25,
            color: Color.fromCssColorString('#38bdf8'), // sky-400
          }),
        },
      })
    } catch (err) {
      console.error('Error drawing trajectory arc on globe:', err)
    }
  }, [trajectoryPoints])

  const handleManualFlyTo = () => {
    const viewer = viewerRef.current
    if (!viewer || viewer.isDestroyed()) return
    const entity = viewer.entities.getById('satellite-point')
    if (entity) {
      viewer.flyTo(entity, {
        duration: 1.5,
        offset: new HeadingPitchRange(0.0, -Math.PI / 4, 3000000),
      })
    }
  }

  // Use inline style for height to guarantee Cesium's canvas has non-zero dimensions.
  // Tailwind h-full requires an ancestor with an explicit height — inline style
  // avoids that CSS cascade dependency and ensures Cesium mounts into a visible div.
  return (
    <div
      style={{ position: 'relative', width: '100%', height: '100%', minHeight: '600px' }}
      className="bg-slate-950 overflow-hidden rounded-lg border border-slate-800"
    >
      <div
        ref={containerRef}
        style={{ width: '100%', height: '100%', minHeight: '600px' }}
      />

      {/* Fly-to Camera Control Button */}
      {satelliteState && (
        <div className="absolute top-4 right-4 z-10 flex gap-2">
          <button
            type="button"
            onClick={handleManualFlyTo}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-slate-900/90 hover:bg-slate-800 text-cyan-400 border border-slate-700 text-xs font-medium backdrop-blur shadow-lg transition-colors cursor-pointer"
            title="Focus camera on satellite"
          >
            <span>🎯</span>
            <span>Fly To Satellite</span>
          </button>
        </div>
      )}
    </div>
  )
}
