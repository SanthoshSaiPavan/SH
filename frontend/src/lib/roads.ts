import { z } from 'zod'
import { api } from './api'
import type { Hub } from './schemas'

/** Road geometry per directed hub pair ("A|B" → [lng, lat][]), fetched on demand and kept for
 *  the session. Pairs the backend has no road for are remembered as straight lines. */
const cache = new Map<string, [number, number][] | null>()
const RoadsSchema = z.record(z.string(), z.array(z.tuple([z.number(), z.number()])))

const key = (a: string, b: string) => `${a}|${b}`

export function hubPairs(hubIds: string[]): [string, string][] {
  return hubIds.slice(1).map((b, i) => [hubIds[i], b])
}

/** Fetch any pairs not cached yet. Resolves to true if new geometry arrived. */
export async function ensureRoadPaths(pairs: [string, string][]): Promise<boolean> {
  const missing = [...new Set(pairs.map(([a, b]) => key(a, b)))].filter((k) => !cache.has(k))
  if (missing.length === 0) return false
  const found = await api.get(`/api/road-routes?pairs=${encodeURIComponent(missing.join(','))}`, RoadsSchema)
  missing.forEach((k) => {
    const path = found[k]
    cache.set(k, path ? path.map(([lat, lng]) => [lng, lat]) : null)
  })
  return Object.keys(found).length > 0
}

/** [lng, lat] coordinates through a hub sequence, following roads where known. */
export function hubLine(hubIds: string[], hubs: Record<string, Hub>): [number, number][] {
  const coords: [number, number][] = []
  hubPairs(hubIds.filter((h) => hubs[h])).forEach(([a, b]) => {
    const road = cache.get(key(a, b))
    const seg: [number, number][] = road ?? [[hubs[a].lng, hubs[a].lat], [hubs[b].lng, hubs[b].lat]]
    coords.push(...(coords.length ? seg.slice(1) : seg))
  })
  return coords
}
