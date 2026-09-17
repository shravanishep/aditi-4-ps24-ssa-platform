import datetime

from .calculations import calculate_distance, calculate_relative_velocity
from .models import CloseApproachResult
from .sgp4_propagator import propagate_orbit


def _ensure_utc(dt: datetime.datetime) -> datetime.datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def find_closest_approach(
    sat1_row,
    sat2_row,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
    threshold_km: float,
    coarse_step_sec: float = 60.0,
    fine_step_sec: float = 1.0,
) -> CloseApproachResult:
    """Find the approximate Time of Closest Approach (TCA) using a coarse-to-fine search."""
    
    norad1 = int(sat1_row["NORAD_CAT_ID"])
    norad2 = int(sat2_row["NORAD_CAT_ID"])
    if norad1 == norad2:
        raise ValueError("sat1 and sat2 must have different NORAD IDs.")
    
    start_utc = _ensure_utc(start_time)
    end_utc = _ensure_utc(end_time)
    
    if end_utc <= start_utc:
        raise ValueError("end_time must be greater than start_time.")
    
    if threshold_km <= 0:
        raise ValueError("threshold_km must be greater than 0.")
    if coarse_step_sec <= 0:
        raise ValueError("coarse_step_sec must be greater than 0.")
    if fine_step_sec <= 0:
        raise ValueError("fine_step_sec must be greater than 0.")
    if fine_step_sec > coarse_step_sec:
        raise ValueError("fine_step_sec must be less than or equal to coarse_step_sec.")

    def evaluate_at(dt: datetime.datetime):
        state1 = propagate_orbit(sat1_row, dt)
        state2 = propagate_orbit(sat2_row, dt)
        
        if state1.sgp4_error != 0 or state2.sgp4_error != 0:
            err = state1.error_message or state2.error_message or "SGP4 Error"
            return None, err
        
        dist = calculate_distance(state1, state2)
        return dist, None

    # Coarse Search
    current_time = start_utc
    min_coarse_dist = float('inf')
    coarse_tca = None
    errors = []

    while current_time <= end_utc:
        dist, err = evaluate_at(current_time)
        if err:
            errors.append(f"At {current_time}: {err}")
        elif dist is not None and dist < min_coarse_dist:
            min_coarse_dist = dist
            coarse_tca = current_time
        
        current_time += datetime.timedelta(seconds=coarse_step_sec)
        
    if current_time - datetime.timedelta(seconds=coarse_step_sec) < end_utc:
        dist, err = evaluate_at(end_utc)
        if err:
             errors.append(f"At {end_utc}: {err}")
        elif dist is not None and dist < min_coarse_dist:
            min_coarse_dist = dist
            coarse_tca = end_utc

    if coarse_tca is None:
        raise ValueError(f"No valid SGP4 states found during coarse search. Errors: {errors}")

    # Fine Search
    fine_start = max(start_utc, coarse_tca - datetime.timedelta(seconds=coarse_step_sec))
    fine_end = min(end_utc, coarse_tca + datetime.timedelta(seconds=coarse_step_sec))
    
    current_time = fine_start
    min_fine_dist = float('inf')
    fine_tca = None
    
    while current_time <= fine_end:
        dist, err = evaluate_at(current_time)
        if not err and dist is not None and dist < min_fine_dist:
            min_fine_dist = dist
            fine_tca = current_time
            
        current_time += datetime.timedelta(seconds=fine_step_sec)
        
    if current_time - datetime.timedelta(seconds=fine_step_sec) < fine_end:
        dist, err = evaluate_at(fine_end)
        if not err and dist is not None and dist < min_fine_dist:
            min_fine_dist = dist
            fine_tca = fine_end

    if fine_tca is None:
        raise ValueError(f"No valid SGP4 states found during fine search. Errors: {errors}")

    final_state1 = propagate_orbit(sat1_row, fine_tca)
    final_state2 = propagate_orbit(sat2_row, fine_tca)
    
    if final_state1.sgp4_error != 0 or final_state2.sgp4_error != 0:
        err1 = final_state1.error_message or "SGP4 Error"
        err2 = final_state2.error_message or "SGP4 Error"
        raise ValueError(f"SGP4 error at final TCA calculation: {err1} | {err2}")
    
    rel_vel_vec = calculate_relative_velocity(final_state1, final_state2)
    rel_speed = float((rel_vel_vec[0]**2 + rel_vel_vec[1]**2 + rel_vel_vec[2]**2)**0.5)

    error_msg = "; ".join(errors) if errors else ""

    return CloseApproachResult(
        object1_norad_id=norad1,
        object2_norad_id=norad2,
        object1_name=str(sat1_row.get("OBJECT_NAME", "")).strip(),
        object2_name=str(sat2_row.get("OBJECT_NAME", "")).strip(),
        analysis_start_time=start_utc,
        analysis_end_time=end_utc,
        time_of_closest_approach=fine_tca,
        minimum_separation_km=min_fine_dist,
        relative_speed_km_s=rel_speed,
        threshold_km=threshold_km,
        is_candidate_close_approach=(min_fine_dist <= threshold_km),
        error_message=error_msg,
    )
