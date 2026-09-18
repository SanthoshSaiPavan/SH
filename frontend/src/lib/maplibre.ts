import * as maplibregl from 'maplibre-gl'
// maplibre-gl v6 loads its worker relative to its own module URL, which breaks once
// Vite pre-bundles it. Bundle the worker explicitly and hand maplibre its URL.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'

maplibregl.setWorkerUrl(workerUrl)

export default maplibregl
