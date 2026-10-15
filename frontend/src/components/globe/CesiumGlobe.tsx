import React, { useEffect, useRef } from 'react'
import {
  buildModuleUrl,
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
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  TileMapServiceImageryProvider,
  Transforms,
  VerticalOrigin,
  Viewer,
} from 'cesium'
import 'cesium/Build/Cesium/Widgets/widgets.css'
import type {
  PropagatedOrbitStateResponse,
  TrajectoryPointResponse,
  MultiPropagatedObjectState,
} from '../../types/api'

/**
 * Convert a TEME position (from SGP4) to the Cesium pseudo-fixed
 * Earth-fixed frame used for rendering on the globe.
 */
export function temeToFixedFrame(
  xKm: number,
  yKm: number,
  zKm: number,
  utcIso: string,
): Cartesian3 {
  const julianDate = JulianDate.fromIso8601(utcIso)
  const rotMatrix = Transforms.computeTemeToPseudoFixedMatrix(julianDate)
  const temeMeters = new Cartesian3(xKm * 1000, yKm * 1000, zKm * 1000)
  return Matrix3.multiplyByVector(rotMatrix, temeMeters, new Cartesian3())
}

interface CesiumGlobeProps {
  satelliteState?: PropagatedOrbitStateResponse | null
  trajectoryPoints?: TrajectoryPointResponse[] | null
  multiObjects?: MultiPropagatedObjectState[] | null
  selectedNoradId?: number | null
  showOrbitTrack?: boolean
  timestampIso?: string
  onSelectObject?: (noradId: number) => void
  onFlyToReady?: (flyToFn: () => void) => void
}

export default function CesiumGlobe({
  satelliteState = null,
  trajectoryPoints = null,
  multiObjects = null,
  selectedNoradId = null,
  showOrbitTrack = true,
  timestampIso,
  onSelectObject,
  onFlyToReady,
}: CesiumGlobeProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const viewerRef = useRef<Viewer | null>(null)
  const handlerRef = useRef<ScreenSpaceEventHandler | null>(null)

  // Use refs for callbacks and active selection so viewer is NEVER destroyed on selection change
  const onSelectObjectRef = useRef(onSelectObject)
  onSelectObjectRef.current = onSelectObject

  const selectedNoradRef = useRef(selectedNoradId)
  selectedNoradRef.current = selectedNoradId

  // Initialize Cesium Viewer ONCE on mount
  useEffect(() => {
    if (!containerRef.current || viewerRef.current) return

    const ionToken = import.meta.env.VITE_CESIUM_ION_TOKEN
    if (ionToken) {
      Ion.defaultAccessToken = ionToken
    }

    // Create Viewer
    const viewer = new Viewer(containerRef.current, {
      baseLayer: false,
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

    // 1. Ensure Earth globe ellipsoid is illuminated and colored vibrant blue even before textures stream
    viewer.scene.globe.baseColor = Color.fromCssColorString('#14355a')
    viewer.scene.globe.showGroundAtmosphere = true
    viewer.scene.globe.enableLighting = false

    // 2. Load Base Imagery: Built-in local NaturalEarthII (100% reliable offline) + Ion/OSM
    const loadImagery = async () => {
      try {
        // Built-in Cesium Natural Earth II texture shipped with Vite build
        const naturalEarthUrl = buildModuleUrl('Assets/Textures/NaturalEarthII')
        const tmsProvider = await TileMapServiceImageryProvider.fromUrl(naturalEarthUrl)
        if (!viewer.isDestroyed()) {
          viewer.imageryLayers.addImageryProvider(tmsProvider)
        }
      } catch (err) {
        console.warn('NaturalEarthII fallback notice:', err)
      }

      // If token provided, layer high-res World Imagery on top
      if (ionToken) {
        try {
          const { IonImageryProvider } = await import('cesium')
          if (!viewer.isDestroyed()) {
            const ionProvider = await IonImageryProvider.fromAssetId(2)
            if (!viewer.isDestroyed()) {
              viewer.imageryLayers.addImageryProvider(ionProvider)
            }
          }
        } catch {
          // keep NaturalEarthII
        }
      } else {
        // Also attempt OpenStreetMap tiles
        try {
          const osmProvider = new OpenStreetMapImageryProvider({
            url: 'https://tile.openstreetmap.org/',
            credit: '© OpenStreetMap contributors',
          })
          if (!viewer.isDestroyed()) {
            viewer.imageryLayers.addImageryProvider(osmProvider)
          }
        } catch {
          // ignore OSM network failure, NaturalEarthII covers it
        }
      }
    }

    void loadImagery()

    // 3. Set standard orbital viewing perspective looking directly at Earth
    viewer.camera.setView({
      destination: Cartesian3.fromDegrees(10.0, 20.0, 24000000.0),
      orientation: {
        heading: 0.0,
        pitch: -Math.PI / 2.0, // directly nadir toward Earth center
        roll: 0.0,
      },
    })

    // 4. Setup ScreenSpaceEventHandler for clicking objects
    const handler = new ScreenSpaceEventHandler(viewer.scene.canvas)
    handlerRef.current = handler

    handler.setInputAction((movement: { position: Cartesian2 }) => {
      const picked = viewer.scene.pick(movement.position)
      if (picked && picked.id) {
        const entityId: string = typeof picked.id === 'string' ? picked.id : picked.id.id
        if (entityId && entityId.startsWith('multiobj-')) {
          const idStr = entityId.replace('multiobj-', '')
          const norad = parseInt(idStr, 10)
          if (!isNaN(norad) && onSelectObjectRef.current) {
            onSelectObjectRef.current(norad)
          }
        }
      }
    }, ScreenSpaceEventType.LEFT_CLICK)

    // 5. Expose flyTo
    const flyToSatellite = () => {
      if (!viewer || viewer.isDestroyed()) return
      const targetId = selectedNoradRef.current
        ? `multiobj-${selectedNoradRef.current}`
        : 'satellite-point'
      const entity = viewer.entities.getById(targetId) || viewer.entities.getById('satellite-point')
      if (entity) {
        viewer.flyTo(entity, {
          duration: 1.5,
          offset: new HeadingPitchRange(0.0, -Math.PI / 4, 3500000),
        })
      } else {
        // Reset to whole Earth
        viewer.camera.flyTo({
          destination: Cartesian3.fromDegrees(10.0, 20.0, 24000000.0),
          duration: 1.5,
        })
      }
    }

    if (onFlyToReady) {
      onFlyToReady(flyToSatellite)
    }

    return () => {
      if (handlerRef.current) {
        handlerRef.current.destroy()
        handlerRef.current = null
      }
      if (viewerRef.current && !viewerRef.current.isDestroyed()) {
        viewerRef.current.destroy()
        viewerRef.current = null
      }
    }
  }, [onFlyToReady]) // ONCE on mount

  // Render Multi-Object Collection entities
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer || viewer.isDestroyed()) return

    // Remove existing multi-object entities
    const toRemove: string[] = []
    viewer.entities.values.forEach((e) => {
      if (e.id.startsWith('multiobj-')) {
        toRemove.push(e.id)
      }
    })
    toRemove.forEach((id) => viewer.entities.removeById(id))

    if (!multiObjects || multiObjects.length === 0) return

    const effectiveTime = timestampIso || new Date().toISOString()

    multiObjects.forEach((obj) => {
      if (obj.sgp4_error !== 0) return

      try {
        const fixedPos = temeToFixedFrame(
          obj.position_x_km,
          obj.position_y_km,
          obj.position_z_km,
          effectiveTime,
        )

        const isSelected = selectedNoradId === obj.norad_cat_id
        let pointColor = Color.fromCssColorString('#22d3ee') // cyan-400 default

        if (isSelected) {
          pointColor = Color.fromCssColorString('#f59e0b') // amber-400 highlight
        } else if (obj.is_stale) {
          pointColor = Color.fromCssColorString('#fbbf24') // amber-300
        } else if (obj.altitude_km > 35000) {
          pointColor = Color.fromCssColorString('#34d399') // emerald-400 (GEO)
        } else if (obj.altitude_km > 2000) {
          pointColor = Color.fromCssColorString('#60a5fa') // blue-400 (MEO)
        }

        viewer.entities.add({
          id: `multiobj-${obj.norad_cat_id}`,
          name: `${obj.object_name} [${obj.norad_cat_id}]`,
          position: fixedPos,
          point: {
            pixelSize: isSelected ? 12 : 8,
            color: pointColor,
            outlineColor: isSelected ? Color.WHITE : Color.fromAlpha(Color.BLACK, 0.7),
            outlineWidth: isSelected ? 2 : 1,
          },
          label: isSelected
            ? {
                text: `${obj.object_name} [${obj.norad_cat_id}]\n${Math.round(obj.altitude_km)} km`,
                font: '11px ui-monospace, monospace',
                fillColor: Color.WHITE,
                outlineColor: Color.BLACK,
                outlineWidth: 2,
                style: LabelStyle.FILL_AND_OUTLINE,
                verticalOrigin: VerticalOrigin.BOTTOM,
                pixelOffset: new Cartesian2(0, -14),
              }
            : undefined,
        })
      } catch (err) {
        // skip placement errors
      }
    })
  }, [multiObjects, selectedNoradId, timestampIso])

  // Single satellite state entity
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
          pixelSize: 12,
          color: Color.fromCssColorString('#f59e0b'), // amber-400
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

      // Fly camera to satellite
      viewer.flyTo(entity, {
        duration: 1.8,
        offset: new HeadingPitchRange(0.0, -Math.PI / 4, 4000000),
      })
    } catch (err) {
      console.error('Error positioning single satellite:', err)
    }
  }, [satelliteState])

  // Single satellite trajectory arc
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer || viewer.isDestroyed()) return

    const existingTraj = viewer.entities.getById('satellite-trajectory')
    if (existingTraj) {
      viewer.entities.remove(existingTraj)
    }

    if (!showOrbitTrack || !trajectoryPoints || trajectoryPoints.length < 2) return

    try {
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
  }, [trajectoryPoints, showOrbitTrack])

  const handleManualFlyTo = () => {
    const viewer = viewerRef.current
    if (!viewer || viewer.isDestroyed()) return
    const targetId = selectedNoradRef.current
      ? `multiobj-${selectedNoradRef.current}`
      : 'satellite-point'
    const entity = viewer.entities.getById(targetId) || viewer.entities.getById('satellite-point')
    if (entity) {
      viewer.flyTo(entity, {
        duration: 1.5,
        offset: new HeadingPitchRange(0.0, -Math.PI / 4, 3500000),
      })
    } else {
      viewer.camera.flyTo({
        destination: Cartesian3.fromDegrees(10.0, 20.0, 24000000.0),
        duration: 1.5,
      })
    }
  }

  return (
    <div
      style={{ position: 'relative', width: '100%', height: '100%', minHeight: '600px' }}
      className="bg-slate-950 overflow-hidden rounded-lg border border-slate-800"
    >
      <div
        ref={containerRef}
        style={{ width: '100%', height: '100%', minHeight: '600px' }}
      />

      {/* Floating Camera and Legend Controls */}
      <div className="absolute top-4 right-4 z-10 flex flex-col items-end gap-2">
        <button
          type="button"
          onClick={handleManualFlyTo}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-slate-900/90 hover:bg-slate-800 text-cyan-400 border border-slate-700 text-xs font-medium backdrop-blur shadow-lg transition-colors cursor-pointer"
          title="Focus camera on selected object"
        >
          <span>🎯</span>
          <span>Focus Camera</span>
        </button>

        {/* Legend */}
        {multiObjects && multiObjects.length > 0 && (
          <div className="bg-slate-900/90 border border-slate-800 rounded p-2.5 text-[10px] text-slate-300 backdrop-blur shadow space-y-1.5">
            <div className="font-semibold text-slate-400 uppercase tracking-wider text-[9px]">
              Object Legend
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-cyan-400" />
              <span>LEO (&lt;2k km)</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-blue-400" />
              <span>MEO (2k–35k km)</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
              <span>GEO (~35.8k km)</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
              <span>Selected / Stale</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
