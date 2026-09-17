import type { SatelliteGPInfo } from '../../types/api'
import InfoCard from '../common/InfoCard'

export default function SatelliteInfo({ data }: { data: SatelliteGPInfo }) {
  return (
    <div>
      <div className="mb-4">
        <h3 className="text-slate-100 font-semibold text-base">{data.object_name}</h3>
        <p className="text-xs text-slate-500 mt-0.5">NORAD {data.norad_cat_id}</p>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
        <InfoCard label="Epoch" value={data.epoch} />
        <InfoCard label="Mean Motion (rev/day)" value={data.mean_motion.toFixed(8)} mono />
        <InfoCard label="Eccentricity" value={data.eccentricity.toFixed(7)} mono />
        <InfoCard label="Inclination (°)" value={data.inclination.toFixed(4)} mono />
        <InfoCard label="RA of Asc Node (°)" value={data.ra_of_asc_node.toFixed(4)} mono />
        <InfoCard label="Arg of Pericenter (°)" value={data.arg_of_pericenter.toFixed(4)} mono />
        <InfoCard label="Mean Anomaly (°)" value={data.mean_anomaly.toFixed(4)} mono />
        <InfoCard label="BSTAR" value={data.bstar.toExponential(4)} mono />
        <InfoCard label="Object ID" value={data.object_id} mono />
      </div>
    </div>
  )
}
