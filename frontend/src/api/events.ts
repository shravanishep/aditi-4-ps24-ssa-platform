import apiFetch from './client'
import type {
  EventListResponse,
  EventResponse,
  LogEventRequest,
} from '../types/api'

export interface EventQueryParams {
  norad_id?: number
  event_type?: string
  classification?: string
  since?: string
  until?: string
  limit?: number
}

/**
 * Fetch persistent event history from the SQLite event store.
 */
export const getEvents = (params?: EventQueryParams): Promise<EventListResponse> => {
  const query = new URLSearchParams()
  if (params?.norad_id) query.set('norad_id', String(params.norad_id))
  if (params?.event_type) query.set('event_type', params.event_type)
  if (params?.classification) query.set('classification', params.classification)
  if (params?.since) query.set('since', params.since)
  if (params?.until) query.set('until', params.until)
  if (params?.limit) query.set('limit', String(params.limit))

  const qs = query.toString()
  return apiFetch<EventListResponse>(`/events${qs ? `?${qs}` : ''}`)
}

/**
 * Retrieve a single event record by ID.
 */
export const getEvent = (eventId: string): Promise<EventResponse> =>
  apiFetch<EventResponse>(`/events/${eventId}`)

/**
 * Log a new event into the persistent timeline.
 */
export const logEvent = (req: LogEventRequest): Promise<EventResponse> =>
  apiFetch<EventResponse>('/events', {
    method: 'POST',
    body: JSON.stringify(req),
  })

/**
 * Retrieve statistical counts of events by type and classification.
 */
export const getEventStats = (): Promise<{
  total: number
  by_type: Record<string, number>
  by_classification: Record<string, number>
}> => apiFetch('/events/stats')

