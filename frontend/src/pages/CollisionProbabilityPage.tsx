import { useState } from 'react'
import { parseCDM, computePc, computePcFromCDM } from '../api/probability'
import { ApiError } from '../api/client'
import type { CDMParseResponse, PcComputeResponse } from '../types/api'
import LoadingSpinner from '../components/common/LoadingSpinner'
import ErrorMessage from '../components/common/ErrorMessage'

const SAMPLE_TEST_CDM = `CCSDS_CDM_VERS = 1.0
COMMENT = Sample Conjunction Data Message with RTN Positional Covariance
CREATION_DATE = 2026-11-13T12:00:00Z
TCA = 2026-11-14T08:30:00Z
MISS_DISTANCE = 0.850
RELATIVE_SPEED = 14.250
RELATIVE_POSITION_R = 0.200
RELATIVE_POSITION_T = 0.100
RELATIVE_POSITION_N = 0.800
OBJECT1_DESIGNATOR = 25544
OBJECT1_NAME = ISS (ZARYA)
OBJECT2_DESIGNATOR = 99001
OBJECT2_NAME = DEBRIS-FRAG-A
COV_FRAME = RTN
COV_RR = 0.250
COV_RT = 0.000
COV_RN = 0.000
COV_TT = 1.000
COV_TN = 0.000
COV_NN = 0.250`

export default function CollisionProbabilityPage() {
  const [activeTab, setActiveTab] = useState<'cdm' | 'manual'>('cdm')

  // CDM parser state
  const [cdmText, setCdmText] = useState(SAMPLE_TEST_CDM)
  const [cdmParsed, setCdmParsed] = useState<CDMParseResponse | null>(null)
  const [cdmPcResult, setCdmPcResult] = useState<PcComputeResponse | null>(null)
  const [cdmLoading, setCdmLoading] = useState(false)
  const [cdmError, setCdmError] = useState<string | null>(null)

  // Manual calculator state
  const [manualMissKm, setManualMissKm] = useState<number>(0.85)
  const [manualSpeedKmS, setManualSpeedKmS] = useState<number>(14.25)
  const [manualHbrM, setManualHbrM] = useState<number>(20.0) // 20 meters
  const [covSigmaR, setCovSigmaR] = useState<number>(0.5) // km (1-sigma radial)
  const [covSigmaT, setCovSigmaT] = useState<number>(1.0) // km (1-sigma along-track)
  const [covSigmaN, setCovSigmaN] = useState<number>(0.5) // km (1-sigma cross-track)
  const [includeCovariance, setIncludeCovariance] = useState<boolean>(true)

  const [manualResult, setManualResult] = useState<PcComputeResponse | null>(null)
  const [manualLoading, setManualLoading] = useState(false)
  const [manualError, setManualError] = useState<string | null>(null)

  async function handleParseCDM() {
    setCdmLoading(true)
    setCdmError(null)
    setCdmParsed(null)
    setCdmPcResult(null)
    try {
      const data = await parseCDM({ cdm_text: cdmText })
      setCdmParsed(data)
    } catch (err) {
      if (err instanceof ApiError) {
        setCdmError(`API Error (${err.status}): ${err.message}`)
      } else {
        setCdmError('Failed to parse CDM message. Verify syntax and key-value structure.')
      }
    } finally {
      setCdmLoading(false)
    }
  }

  async function handleComputeFromCDM() {
    setCdmLoading(true)
    setCdmError(null)
    try {
      const data = await computePcFromCDM({ cdm_text: cdmText, hard_body_radius_km: 0.020 })
      setCdmPcResult(data.pc_result)
    } catch (err) {
      if (err instanceof ApiError) {
        setCdmError(`API Error (${err.status}): ${err.message}`)
      } else {
        setCdmError('Failed to compute collision probability from CDM. Check covariance validity.')
      }
    } finally {
      setCdmLoading(false)
    }
  }

  async function handleComputeManual(e: React.FormEvent) {
    e.preventDefault()
    setManualLoading(true)
    setManualError(null)
    try {
      const covMatrix = includeCovariance
        ? [
            [covSigmaR ** 2, 0, 0],
            [0, covSigmaT ** 2, 0],
            [0, 0, covSigmaN ** 2],
          ]
        : null

      const data = await computePc({
        miss_distance_km: manualMissKm,
        rel_speed_km_s: manualSpeedKmS,
        hard_body_radius_km: manualHbrM / 1000.0,
        cov1_rtn: covMatrix,
        cov2_rtn: covMatrix,
      })
      setManualResult(data)
    } catch (err) {
      if (err instanceof ApiError) {
        setManualError(`API Error (${err.status}): ${err.message}`)
      } else {
        setManualError('Failed to compute manual Pc calculation.')
      }
    } finally {
      setManualLoading(false)
    }
  }

  const formatPc = (val: number | null) => {
    if (val === null || val === undefined) return 'Unavailable'
    if (val === 0) return '0.000000 (Effectively Zero)'
    if (val < 1e-4) return val.toExponential(4)
    return val.toFixed(6)
  }

  return (
    <div className="p-8 max-w-6xl">
      {/* Page Header */}
      <div className="mb-6">
        <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2">
          <span className="text-sky-400 font-mono text-lg">⊗</span> Collision Probability (Pc) & Conjunction Data Messages
        </h1>
        <p className="text-slate-400 text-sm mt-1">
          Foster's (1992) 2-D encounter-plane method with CCSDS Conjunction Data Message (CDM) standard ingestion.
        </p>
      </div>

      {/* Advisory Banner: Clean plain text without unrendered LaTeX */}
      <div className="bg-slate-800/80 border border-slate-700 rounded-lg p-4 mb-6 flex items-start gap-3 text-xs text-slate-300">
        <span className="text-sky-400 font-bold text-sm leading-none mt-0.5">ℹ</span>
        <div className="space-y-1">
          <p className="font-semibold text-slate-200">
            Strict Covariance Requirement for Physical Collision Probability (Pc):
          </p>
          <p className="text-slate-400 leading-relaxed">
            Collision probability (Pc) mathematically represents the integral of relative positional uncertainty over a combined spherical collision volume. It requires physical uncertainty quantified by a 3×3 position covariance matrix. Public two-line element (TLE) sets do not supply covariance; therefore, Pc is strictly marked as <strong className="text-slate-200">Unavailable</strong> when covariance is absent. The heuristic Threat Prioritization score used elsewhere in this platform is an operational screening indicator, not a validated physical collision probability.
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-700 mb-6">
        <button
          onClick={() => setActiveTab('cdm')}
          className={`py-2 px-5 text-xs font-semibold border-b-2 transition-colors ${
            activeTab === 'cdm'
              ? 'border-sky-500 text-sky-300'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          CCSDS CDM Message Parser
        </button>
        <button
          onClick={() => setActiveTab('manual')}
          className={`py-2 px-5 text-xs font-semibold border-b-2 transition-colors ${
            activeTab === 'manual'
              ? 'border-sky-500 text-sky-300'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          Manual Encounter Calculator
        </button>
      </div>

      {/* Tab 1: CDM Ingestion */}
      {activeTab === 'cdm' && (
        <div className="space-y-6">
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-medium text-slate-300 flex items-center gap-2">
                <span>Conjunction Data Message (ASCII / KVN format)</span>
                <span className="text-[10px] bg-slate-700/80 text-slate-400 px-2 py-0.5 rounded font-mono">
                  Sample Test Data
                </span>
              </label>
              <button
                type="button"
                onClick={() => setCdmText(SAMPLE_TEST_CDM)}
                className="text-xs text-sky-400 hover:text-sky-300 transition-colors"
              >
                Reset to Sample CDM
              </button>
            </div>

            <textarea
              rows={12}
              value={cdmText}
              onChange={(e) => setCdmText(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 rounded p-3 font-mono text-xs text-slate-200 focus:outline-none focus:border-sky-500 leading-relaxed"
              placeholder="Paste CCSDS CDM ASCII text here..."
            />

            <div className="flex flex-wrap gap-3 mt-4">
              <button
                onClick={handleParseCDM}
                disabled={cdmLoading}
                className="bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-slate-100 px-4 py-2 rounded text-xs font-medium transition-colors"
              >
                {cdmLoading ? <LoadingSpinner size="sm" /> : 'Parse CDM Structure'}
              </button>
              <button
                onClick={handleComputeFromCDM}
                disabled={cdmLoading}
                className="bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white px-5 py-2 rounded text-xs font-medium transition-colors"
              >
                {cdmLoading ? <LoadingSpinner size="sm" /> : 'Evaluate Foster 2D Collision Probability'}
              </button>
            </div>
          </div>

          {cdmError && <ErrorMessage message={cdmError} />}

          {/* CDM Parsed Inspection Details */}
          {cdmParsed && (
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-5 text-xs space-y-4">
              <div className="flex items-center justify-between border-b border-slate-700 pb-2">
                <h3 className="font-semibold text-slate-200">
                  1. CDM Inspection & Covariance Validation
                </h3>
                <span
                  className={`px-2 py-0.5 rounded text-[11px] font-medium border ${
                    cdmParsed.covariance_valid
                      ? 'bg-emerald-950/80 text-emerald-400 border-emerald-700/60'
                      : 'bg-rose-950/80 text-rose-400 border-rose-700/60'
                  }`}
                >
                  {cdmParsed.covariance_valid ? 'Valid RTN Covariance (Positive Semi-Definite)' : 'Covariance Missing or Invalid'}
                </span>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-slate-900/60 p-2.5 rounded border border-slate-700/50">
                  <span className="text-slate-400 block text-[11px]">Primary Object</span>
                  <span className="font-semibold text-slate-200 font-mono">{cdmParsed.object1_name}</span>
                </div>
                <div className="bg-slate-900/60 p-2.5 rounded border border-slate-700/50">
                  <span className="text-slate-400 block text-[11px]">Secondary Object</span>
                  <span className="font-semibold text-slate-200 font-mono">{cdmParsed.object2_name}</span>
                </div>
                <div className="bg-slate-900/60 p-2.5 rounded border border-slate-700/50">
                  <span className="text-slate-400 block text-[11px]">Time of Closest Approach</span>
                  <span className="font-mono text-slate-200">{new Date(cdmParsed.tca).toUTCString()}</span>
                </div>
                <div className="bg-slate-900/60 p-2.5 rounded border border-slate-700/50">
                  <span className="text-slate-400 block text-[11px]">Relative Speed</span>
                  <span className="font-mono text-slate-200 font-semibold">{cdmParsed.relative_speed_km_s.toFixed(2)} km/s</span>
                </div>
              </div>

              {cdmParsed.parse_notes.length > 0 && (
                <div className="bg-slate-900/40 p-2.5 rounded text-[11px] text-slate-400 space-y-1">
                  <span className="font-medium text-slate-300">Parser Notes:</span>
                  <ul className="list-disc list-inside space-y-0.5">
                    {cdmParsed.parse_notes.map((n, i) => (
                      <li key={i}>{n}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* CDM Pc Result */}
          {cdmPcResult && (
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-5 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-700 pb-3">
                <h3 className="text-sm font-bold text-slate-100">
                  2. Foster 2-D Collision Probability Evaluation
                </h3>
                <span className="text-xs px-2.5 py-1 rounded bg-slate-900 text-slate-300 font-mono border border-slate-700">
                  Method: {cdmPcResult.pc_method}
                </span>
              </div>

              {cdmPcResult.pc !== null ? (
                <div className="p-4 bg-slate-900 rounded-lg border border-slate-700 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <span className="text-xs text-slate-400 block">Calculated Collision Probability (Pc)</span>
                    <span className="text-2xl font-bold font-mono text-sky-400 mt-1 block">
                      {formatPc(cdmPcResult.pc)}
                    </span>
                    <span className="text-[11px] text-slate-500 mt-0.5 block">
                      Evaluated for combined hard-body radius R = {(cdmPcResult.hard_body_radius_km * 1000).toFixed(0)} meters
                    </span>
                  </div>
                  <div className="text-left md:text-right text-xs text-slate-400 space-y-1.5">
                    <div>
                      Encounter Plane Major σ₁: <span className="font-mono text-slate-200 font-semibold">{cdmPcResult.b_plane_sigma1_km?.toFixed(3)} km</span>
                    </div>
                    <div>
                      Encounter Plane Minor σ₂: <span className="font-mono text-slate-200 font-semibold">{cdmPcResult.b_plane_sigma2_km?.toFixed(3)} km</span>
                    </div>
                    <div>
                      Covariance Status: <span className="text-emerald-400 font-medium">Valid Positive Semi-Definite</span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="p-4 bg-amber-950/40 border border-amber-800/80 rounded-lg text-xs text-amber-300">
                  ⚠️ Collision probability unavailable – valid covariance data required.
                </div>
              )}

              {cdmPcResult.computation_notes.length > 0 && (
                <div className="text-xs text-slate-400 space-y-1 bg-slate-900/40 p-3 rounded border border-slate-700/60">
                  <span className="font-medium text-slate-300 block">Evaluation Details:</span>
                  <ul className="list-disc list-inside space-y-0.5 text-slate-400">
                    {cdmPcResult.computation_notes.map((note, i) => (
                      <li key={i}>{note}</li>
                    ))}
                  </ul>
                </div>
              )}

              <p className="text-[11px] text-slate-500 italic">
                Notice: {cdmPcResult.disclaimer}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Manual Calculator */}
      {activeTab === 'manual' && (
        <div className="space-y-6">
          <form onSubmit={handleComputeManual} className="bg-slate-800 border border-slate-700 rounded-lg p-5 space-y-4">
            <h3 className="text-sm font-semibold text-slate-200 border-b border-slate-700 pb-2">
              Encounter Geometry & Collision Geometry
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Miss Distance (km)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0.001"
                  value={manualMissKm}
                  onChange={(e) => setManualMissKm(parseFloat(e.target.value) || 0.1)}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-1.5 text-xs text-slate-100 font-mono"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Relative Velocity (km/s)
                </label>
                <input
                  type="number"
                  step="0.1"
                  min="0.1"
                  value={manualSpeedKmS}
                  onChange={(e) => setManualSpeedKmS(parseFloat(e.target.value) || 1.0)}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-1.5 text-xs text-slate-100 font-mono"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Combined Hard-Body Radius (meters)
                </label>
                <input
                  type="number"
                  step="1"
                  min="1"
                  max="1000"
                  value={manualHbrM}
                  onChange={(e) => setManualHbrM(parseFloat(e.target.value) || 20.0)}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-1.5 text-xs text-slate-100 font-mono"
                  required
                />
              </div>
            </div>

            <div className="pt-2 border-t border-slate-700">
              <div className="flex items-center gap-2 mb-3">
                <input
                  type="checkbox"
                  id="includeCov"
                  checked={includeCovariance}
                  onChange={(e) => setIncludeCovariance(e.target.checked)}
                  className="rounded border-slate-700 bg-slate-900 text-sky-500 focus:ring-0"
                />
                <label htmlFor="includeCov" className="text-xs font-medium text-slate-300 cursor-pointer">
                  Provide Positional Covariance (Diagonal 1-σ uncertainties in RTN frame)
                </label>
              </div>

              {includeCovariance ? (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 bg-slate-900/60 p-3.5 rounded border border-slate-700/60">
                  <div>
                    <label className="block text-[11px] text-slate-400 mb-1">Radial 1-σ (km)</label>
                    <input
                      type="number"
                      step="0.05"
                      min="0.01"
                      value={covSigmaR}
                      onChange={(e) => setCovSigmaR(parseFloat(e.target.value) || 0.1)}
                      className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1 text-xs text-slate-100 font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-slate-400 mb-1">Along-Track 1-σ (km)</label>
                    <input
                      type="number"
                      step="0.05"
                      min="0.01"
                      value={covSigmaT}
                      onChange={(e) => setCovSigmaT(parseFloat(e.target.value) || 0.1)}
                      className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1 text-xs text-slate-100 font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-slate-400 mb-1">Cross-Track 1-σ (km)</label>
                    <input
                      type="number"
                      step="0.05"
                      min="0.01"
                      value={covSigmaN}
                      onChange={(e) => setCovSigmaN(parseFloat(e.target.value) || 0.1)}
                      className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1 text-xs text-slate-100 font-mono"
                    />
                  </div>
                </div>
              ) : (
                <div className="p-3 bg-amber-950/20 border border-amber-900/40 rounded text-xs text-amber-300/90">
                  Notice: Covariance disabled. Without positional uncertainty data, collision probability cannot be evaluated and will report <em>Unavailable</em>.
                </div>
              )}
            </div>

            <button
              type="submit"
              disabled={manualLoading}
              className="bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white px-5 py-2 rounded text-xs font-medium transition-colors"
            >
              {manualLoading ? <LoadingSpinner size="sm" /> : 'Compute Collision Probability'}
            </button>
          </form>

          {manualError && <ErrorMessage message={manualError} />}

          {manualResult && (
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-5 space-y-4">
              <h3 className="text-sm font-bold text-slate-100 border-b border-slate-700 pb-2">
                Calculation Output
              </h3>

              {manualResult.pc !== null ? (
                <div className="p-4 bg-slate-900 rounded-lg border border-slate-700 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <span className="text-xs text-slate-400 block">Calculated Collision Probability (Pc)</span>
                    <span className="text-2xl font-bold font-mono text-sky-400 mt-1 block">
                      {formatPc(manualResult.pc)}
                    </span>
                  </div>
                  <div className="text-left md:text-right text-xs text-slate-400 space-y-1">
                    <div>
                      Encounter Plane σ₁: <span className="font-mono text-slate-200">{manualResult.b_plane_sigma1_km?.toFixed(3)} km</span>
                    </div>
                    <div>
                      Encounter Plane σ₂: <span className="font-mono text-slate-200">{manualResult.b_plane_sigma2_km?.toFixed(3)} km</span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="p-4 bg-amber-950/40 border border-amber-800/80 rounded-lg text-xs text-amber-300">
                  ⚠️ Collision probability unavailable – valid covariance data required.
                  <p className="mt-1 text-[11px] text-amber-400/80">
                    Enable the "Provide Positional Covariance" checkbox above to compute Pc using Foster's 2-D method.
                  </p>
                </div>
              )}

              {manualResult.computation_notes.length > 0 && (
                <div className="text-xs text-slate-400 space-y-1 bg-slate-900/40 p-3 rounded border border-slate-700/60">
                  <span className="font-medium text-slate-300 block">Notes:</span>
                  <ul className="list-disc list-inside space-y-0.5 text-slate-400">
                    {manualResult.computation_notes.map((note, i) => (
                      <li key={i}>{note}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
