import type { Priority, StrategyType } from './schemas'

export const PRIORITY_META: Record<Priority, { label: string; color: string; emoji: string }> = {
  critical: { label: 'Critical', color: '#ef4444', emoji: '🔴' },
  high: { label: 'High', color: '#f97316', emoji: '🟠' },
  medium: { label: 'Medium', color: '#eab308', emoji: '🟡' },
  low: { label: 'Low', color: '#22c55e', emoji: '🟢' },
}

export const STATUS_COLORS: Record<string, string> = {
  at_origin: '#8892b0', in_transit: '#3b82f6', misplaced: '#ef4444', piggybacked: '#a855f7',
  recovered: '#10b981', delivered: '#10b981', delayed: '#f59e0b',
}

export const STRATEGY_META: Record<StrategyType, { label: string; color: string; icon: string }> = {
  piggyback: { label: 'Piggyback', color: '#a855f7', icon: '🚚' },
  reroute: { label: 'Reroute', color: '#3b82f6', icon: '🔀' },
  dedicated: { label: 'Dedicated vehicle', color: '#f59e0b', icon: '🚛' },
  hold: { label: 'Hold at hub', color: '#8892b0', icon: '⏸' },
}

export const CONNECTION_COLORS: Record<string, string> = {
  live: '#10b981', delayed: '#f59e0b', offline: '#ef4444',
}

export const MAP_STYLES: Record<string, any> = {
  road: {
    version: 8 as const,
    sources: {
      osm: {
        type: 'raster' as const,
        tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
        tileSize: 256,
        attribution: '© OpenStreetMap',
      },
    },
    layers: [{ id: 'osm', type: 'raster' as const, source: 'osm' }],
  },
  satellite: {
    version: 8 as const,
    sources: {
      esri: {
        type: 'raster' as const,
        tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
        tileSize: 256,
        attribution: 'Tiles &copy; Esri',
      },
    },
    layers: [{ id: 'esri', type: 'raster' as const, source: 'esri' }],
  },
  terrain: {
    version: 8 as const,
    sources: {
      osm: {
        type: 'raster' as const,
        tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
        tileSize: 256,
        attribution: '© OpenStreetMap',
      },
      terrainSource: {
        type: 'raster-dem' as const,
        tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
        encoding: 'terrarium',
        tileSize: 256,
        maxzoom: 14,
      },
    },
    layers: [{ id: 'osm', type: 'raster' as const, source: 'osm' }],
    terrain: { source: 'terrainSource', exaggeration: 1.5 },
  },
}

export const MAP_CONFIG = {
  center: [79.5, 21.5] as [number, number],
  zoom: 4.3,
}

/** Socket location updates arrive every tick; markers animate over this window. */
export const MARKER_ANIMATION_MS = 2000

/** Chart series colours per strategy: validated categorical palette (dark surface,
 *  CVD ΔE ≥ 8, fixed order) — distinct from the UI accent colours above. */
export const STRATEGY_CHART_COLORS: Record<StrategyType, string> = {
  piggyback: '#3987e5', reroute: '#d95926', dedicated: '#199e70', hold: '#c98500',
}

/** Testing-only: the one driver allowed on /driver, with a no-GPS fallback (mirrors backend STALE_TIMESTAMP_EXEMPT_USER). */
export const TEST_DRIVER_USERNAME = 'driver101'

/** The seeded demo accounts (database/seed_data.py). There is no login page: the app signs in
 *  as one of these, and the user menu switches between them. The backend still issues JWTs and
 *  enforces roles on every request. */
export const DEMO_ACCOUNTS = [
  { username: 'admin', password: 'admin123', label: 'Admin' },
  { username: 'operator', password: 'operator123', label: 'Operator' },
  { username: 'driver101', password: 'driver123', label: 'Driver · TRUCK-101' },
  { username: 'driver102', password: 'driver123', label: 'Driver · TRUCK-102' },
  { username: 'driver103', password: 'driver123', label: 'Driver · TRUCK-103' },
  { username: 'driver104', password: 'driver123', label: 'Driver · TRUCK-104' },
] as const
