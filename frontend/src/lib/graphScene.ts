import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { CSS2DObject, CSS2DRenderer } from 'three/examples/jsm/renderers/CSS2DRenderer.js'
import type { GraphEdge, GraphNode, GraphSnapshot } from './schemas'

export type EdgeLayer = 'leg' | 'wait' | 'board' | 'unload' | 'onboard' | 'detour'
export type CameraPreset = '3d' | 'top' | 'side'

// Unified selection — either a node or an edge was clicked.
export type Selection =
  | { kind: 'node'; node: GraphNode }
  | { kind: 'edge'; edge: GraphEdge }
  | null

export const EDGE_LAYER_META: Record<EdgeLayer, { label: string; color: string }> = {
  leg:     { label: 'Vehicle leg',       color: '#457B9D' },
  wait:    { label: 'Wait (hub timeline)', color: '#A1A1AA' },
  board:   { label: 'Board',             color: '#52B788' },
  unload:  { label: 'Unload',            color: '#F4A261' },
  onboard: { label: 'Stay onboard',      color: '#6366F1' },
  detour:  { label: 'Detour variants',   color: '#E63946' },
}

/** Per-vehicle leg colours, cycled by vehicle order. */
const VEHICLE_COLORS = ['#457B9D', '#52B788', '#F4A261', '#A78BFA', '#4CC9F0', '#F28482', '#E9C46A', '#90BE6D']
const BG          = '#18181A'
const PATH_COLOR  = '#D2D88F'
const ENTRY_COLOR = '#E63946'
const FLOOR_EXTENT = 20
const TIME_HEIGHT  = 14

const CAMERA_POSES: Record<CameraPreset, [number, number, number]> = {
  '3d':  [22, 18, 22],
  top:   [0.01, 36, 0.01],
  side:  [0, 7, 34],
}

type NodePickable = { mesh: THREE.InstancedMesh; nodes: GraphNode[] }
type EdgePickable = { obj: THREE.LineSegments; edges: GraphEdge[] }

export type GraphScene = {
  update:    (snap: GraphSnapshot, layers: Record<EdgeLayer, boolean>) => void
  setLayers: (layers: Record<EdgeLayer, boolean>) => void
  setCamera: (preset: CameraPreset) => void
  select:    (id: string | null) => void
  dispose:   () => void
}

const isDetour = (n: GraphNode | undefined) => !!n?.variant && n.variant !== 'main'

function label(text: string, className: string) {
  const el = document.createElement('div')
  el.className = className
  el.textContent = text
  return new CSS2DObject(el)
}

function disposeTree(obj: THREE.Object3D) {
  obj.traverse((o) => {
    const m = o as THREE.Mesh
    m.geometry?.dispose()
    const mat = m.material as THREE.Material | THREE.Material[] | undefined
    if (Array.isArray(mat)) mat.forEach((x) => x.dispose())
    else mat?.dispose()
    if (o instanceof CSS2DObject) o.element.remove()
  })
}

export function createGraphScene(
  container: HTMLElement,
  onSelect: (sel: Selection) => void,
): GraphScene {
  const renderer = new THREE.WebGLRenderer({ antialias: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.setClearColor(BG)
  container.appendChild(renderer.domElement)

  const labels = new CSS2DRenderer()
  Object.assign(labels.domElement.style, { position: 'absolute', inset: '0', pointerEvents: 'none' })
  container.appendChild(labels.domElement)

  const scene = new THREE.Scene()
  scene.add(new THREE.AmbientLight('#ffffff', 1.6))
  const sun = new THREE.DirectionalLight('#ffffff', 1.4)
  sun.position.set(10, 30, 15)
  scene.add(sun)
  const floor = new THREE.GridHelper(FLOOR_EXTENT * 1.4, 28, '#333336', '#2A2A2D')
  scene.add(floor)

  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 500)
  camera.position.set(...CAMERA_POSES['3d'])
  const controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.target.set(0, TIME_HEIGHT / 2.5, 0)
  controls.maxDistance = 120
  let cameraGoal: THREE.Vector3 | null = null
  controls.addEventListener('start', () => { cameraGoal = null })

  const content = new THREE.Group()
  scene.add(content)
  const edgeObjects: Partial<Record<EdgeLayer, THREE.Object3D>> = {}
  let detourNodes: THREE.Object3D | null = null
  let nodePickables: NodePickable[] = []
  let edgePickables: EdgePickable[] = []
  let positions = new Map<string, THREE.Vector3>()
  let byId     = new Map<string, GraphNode>()

  const ring = new THREE.Mesh(
    new THREE.TorusGeometry(0.42, 0.05, 8, 32),
    new THREE.MeshBasicMaterial({ color: PATH_COLOR }),
  )
  ring.visible = false
  scene.add(ring)

  function resize() {
    const { clientWidth: w, clientHeight: h } = container
    if (!w || !h) return
    renderer.setSize(w, h)
    labels.setSize(w, h)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
  }
  const ro = new ResizeObserver(resize)
  ro.observe(container)
  resize()

  let frame = 0
  const tick = () => {
    frame = requestAnimationFrame(tick)
    if (cameraGoal) {
      camera.position.lerp(cameraGoal, 0.12)
      if (camera.position.distanceTo(cameraGoal) < 0.05) cameraGoal = null
    }
    controls.update()
    if (ring.visible) ring.quaternion.copy(camera.quaternion)
    renderer.render(scene, camera)
    labels.render(scene, camera)
  }
  tick()

  // ── Click / Selection ──────────────────────────────────────────
  const raycaster = new THREE.Raycaster()
  raycaster.params.Line = { threshold: 0.25 }   // world-units tolerance for edge picking
  const down = new THREE.Vector2()

  const onDown = (e: PointerEvent) => down.set(e.clientX, e.clientY)
  const onUp = (e: PointerEvent) => {
    if (down.distanceTo(new THREE.Vector2(e.clientX, e.clientY)) > 4) return
    const rect = renderer.domElement.getBoundingClientRect()
    const ndc = new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1,
    )
    raycaster.setFromCamera(ndc, camera)

    // 1. Try node picks
    const visibleNodes = nodePickables.filter((p) => p.mesh.visible && p.mesh.parent?.visible !== false)
    const nodeHit = raycaster.intersectObjects(visibleNodes.map((p) => p.mesh), false)[0]
    const nodeOwner = nodeHit && visibleNodes.find((p) => p.mesh === nodeHit.object)
    const hitNode = nodeOwner && nodeHit.instanceId !== undefined ? nodeOwner.nodes[nodeHit.instanceId] : null

    // 2. Try edge picks
    const visibleEdges = edgePickables.filter((ep) => ep.obj.visible && ep.obj.parent?.visible !== false)
    const edgeHit = raycaster.intersectObjects(visibleEdges.map((ep) => ep.obj), false)[0]
    const edgeOwner = edgeHit && visibleEdges.find((ep) => ep.obj === edgeHit.object)
    const hitEdge = edgeOwner && edgeHit.faceIndex != null ? edgeOwner.edges[edgeHit.faceIndex] : null

    // 3. Pick whichever is closer; nodes win ties
    let sel: Selection = null
    if (hitNode && hitEdge) {
      sel = nodeHit!.distance <= edgeHit!.distance
        ? { kind: 'node', node: hitNode }
        : { kind: 'edge', edge: hitEdge }
    } else if (hitNode) {
      sel = { kind: 'node', node: hitNode }
    } else if (hitEdge) {
      sel = { kind: 'edge', edge: hitEdge }
    }

    select(sel?.kind === 'node' ? sel.node.id : null)
    onSelect(sel)
  }
  renderer.domElement.addEventListener('pointerdown', onDown)
  renderer.domElement.addEventListener('pointerup', onUp)

  function select(id: string | null) {
    const p = id ? positions.get(id) : undefined
    ring.visible = !!p
    if (p) ring.position.copy(p)
  }

  function setLayers(layers: Record<EdgeLayer, boolean>) {
    for (const [k, obj] of Object.entries(edgeObjects)) obj.visible = layers[k as EdgeLayer]
    if (detourNodes) detourNodes.visible = layers.detour
  }

  function nodeMesh(nodes: GraphNode[], geometry: THREE.BufferGeometry, color: (n: GraphNode) => string) {
    const mesh = new THREE.InstancedMesh(geometry, new THREE.MeshLambertMaterial(), Math.max(nodes.length, 1))
    mesh.count = nodes.length
    const m = new THREE.Matrix4()
    const c = new THREE.Color()
    nodes.forEach((n, i) => {
      mesh.setMatrixAt(i, m.makeTranslation(positions.get(n.id)!))
      mesh.setColorAt(i, c.set(color(n)))
    })
    nodePickables.push({ mesh, nodes })
    return mesh
  }

  function update(snap: GraphSnapshot, layers: Record<EdgeLayer, boolean>) {
    disposeTree(content)
    content.clear()
    nodePickables = []
    edgePickables = []
    for (const k of Object.keys(edgeObjects)) delete edgeObjects[k as EdgeLayer]

    // Hub geography → floor layout
    const lat0 = snap.hubs.reduce((s, h) => s + h.lat, 0) / Math.max(snap.hubs.length, 1)
    const lng0 = snap.hubs.reduce((s, h) => s + h.lng, 0) / Math.max(snap.hubs.length, 1)
    const k = Math.cos((lat0 * Math.PI) / 180)
    const raw = snap.hubs.map((h) => ({ id: h.id, x: (h.lng - lng0) * k, z: -(h.lat - lat0) }))
    const span = Math.max(...raw.map((r) => Math.max(Math.abs(r.x), Math.abs(r.z))), 1e-6)
    const hubXZ = new Map(raw.map((r) => [r.id, [(r.x / span) * (FLOOR_EXTENT / 2), (r.z / span) * (FLOOR_EXTENT / 2)] as const]))
    const yScale = TIME_HEIGHT / snap.hours
    const at = (hub: string, t: number) => {
      const [x, z] = hubXZ.get(hub) ?? [0, 0]
      return new THREE.Vector3(x, t * yScale, z)
    }
    byId      = new Map(snap.nodes.map((n) => [n.id, n]))
    positions = new Map(snap.nodes.map((n) => [n.id, at(n.hub, n.t)]))

    // Hub pillars, bases and labels
    const pillarPts: THREE.Vector3[] = []
    for (const h of snap.hubs) {
      pillarPts.push(at(h.id, 0), at(h.id, snap.hours))
      const base = new THREE.Mesh(
        new THREE.CylinderGeometry(0.55, 0.55, 0.04, 32),
        new THREE.MeshBasicMaterial({ color: PATH_COLOR, transparent: true, opacity: 0.35 }),
      )
      base.position.copy(at(h.id, 0))
      content.add(base)
      const l = label(h.id, 'graph3d-label graph3d-hub')
      l.position.copy(at(h.id, 0)).add(new THREE.Vector3(0, -0.6, 0))
      content.add(l)
    }
    const pillars = new THREE.LineSegments(
      new THREE.BufferGeometry().setFromPoints(pillarPts),
      new THREE.LineDashedMaterial({ color: '#A1A1AA', dashSize: 0.3, gapSize: 0.25, transparent: true, opacity: 0.45 }),
    )
    pillars.computeLineDistances()
    content.add(pillars)

    // Time-axis ticks
    const corner = new THREE.Vector3(-FLOOR_EXTENT * 0.7, 0, FLOOR_EXTENT * 0.7)
    const step = snap.hours <= 12 ? 2 : snap.hours <= 36 ? 4 : 12
    const axis = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([corner, corner.clone().setY(TIME_HEIGHT)]),
      new THREE.LineBasicMaterial({ color: '#71717A' }),
    )
    content.add(axis)
    for (let t = 0; t <= snap.hours; t += step) {
      const l = label(`+${t}h`, 'graph3d-label graph3d-tick')
      l.position.copy(corner).setY(t * yScale)
      content.add(l)
    }

    // Edges — one LineSegments per layer; parallel edge array for raycasting
    const vehicleIds = [...new Set(snap.nodes.flatMap((n) => (n.vehicle_id ? [n.vehicle_id] : [])))].sort()
    const vehicleColor = new Map(vehicleIds.map((v, i) => [v, VEHICLE_COLORS[i % VEHICLE_COLORS.length]]))
    const buckets: Record<EdgeLayer, { pts: number[]; cols: number[]; edges: GraphEdge[] }> = {
      leg:     { pts: [], cols: [], edges: [] },
      wait:    { pts: [], cols: [], edges: [] },
      board:   { pts: [], cols: [], edges: [] },
      unload:  { pts: [], cols: [], edges: [] },
      onboard: { pts: [], cols: [], edges: [] },
      detour:  { pts: [], cols: [], edges: [] },
    }
    const c = new THREE.Color()
    for (const e of snap.edges) {
      const a = positions.get(e.source), b = positions.get(e.target)
      if (!a || !b) continue
      const detour = isDetour(byId.get(e.source)) || isDetour(byId.get(e.target))
      const layer: EdgeLayer = detour ? 'detour' : (e.kind as EdgeLayer)
      if (!buckets[layer]) continue
      c.set(layer === 'leg' && e.vehicle_id ? vehicleColor.get(e.vehicle_id)! : EDGE_LAYER_META[layer].color)
      buckets[layer].pts.push(a.x, a.y, a.z, b.x, b.y, b.z)
      buckets[layer].cols.push(c.r, c.g, c.b, c.r, c.g, c.b)
      buckets[layer].edges.push(e)
    }
    for (const [layer, { pts, cols, edges }] of Object.entries(buckets) as [EdgeLayer, { pts: number[]; cols: number[]; edges: GraphEdge[] }][]) {
      const g = new THREE.BufferGeometry()
      g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
      g.setAttribute('color',    new THREE.Float32BufferAttribute(cols, 3))
      const opacity = layer === 'leg' ? 0.95 : layer === 'detour' ? 0.45 : 0.7
      const obj = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity }))
      edgeObjects[layer] = obj
      edgePickables.push({ obj, edges })
      content.add(obj)
    }

    // Nodes — spheres (dep), cubes (arr), small spheres (hub), small spheres (detour)
    const hubNodes  = snap.nodes.filter((n) => n.kind === 'hub')
    const depNodes  = snap.nodes.filter((n) => n.kind === 'dep' && !isDetour(n))
    const arrNodes  = snap.nodes.filter((n) => n.kind === 'arr' && !isDetour(n))
    const detourAll = snap.nodes.filter((n) => isDetour(n))
    content.add(nodeMesh(hubNodes, new THREE.SphereGeometry(0.11, 10, 8), () => '#A1A1AA'))
    content.add(nodeMesh(depNodes, new THREE.SphereGeometry(0.2, 14, 10), (n) => vehicleColor.get(n.vehicle_id!) ?? '#ffffff'))
    content.add(nodeMesh(arrNodes, new THREE.BoxGeometry(0.25, 0.25, 0.25), (n) => vehicleColor.get(n.vehicle_id!) ?? '#ffffff'))
    detourNodes = nodeMesh(detourAll, new THREE.SphereGeometry(0.14, 10, 8), () => EDGE_LAYER_META.detour.color)
    content.add(detourNodes)

    // Recommended recovery paths: entry → legs → sink (lime tube + red diamond + yellow cone)
    for (const r of snap.recommendations) {
      if (!r.hub) continue
      const pts = [at(r.hub, r.t)]
      let hub = r.hub
      for (const leg of r.legs) {
        if (leg.from_hub !== hub) pts.push(at(leg.from_hub, leg.dep_t))
        pts.push(at(leg.from_hub, leg.dep_t), at(leg.to_hub, leg.arr_t))
        hub = leg.to_hub
      }

      // Lime tube
      const path = new THREE.CurvePath<THREE.Vector3>()
      for (let i = 1; i < pts.length; i++) {
        if (!pts[i].equals(pts[i - 1])) path.add(new THREE.LineCurve3(pts[i - 1], pts[i]))
      }
      if (path.curves.length) {
        content.add(new THREE.Mesh(
          new THREE.TubeGeometry(path, path.curves.length * 16, 0.07, 6, false),
          new THREE.MeshBasicMaterial({ color: PATH_COLOR }),
        ))
      }

      // Entry node (red octahedron)
      const entry = new THREE.Mesh(
        new THREE.OctahedronGeometry(0.35),
        new THREE.MeshLambertMaterial({ color: ENTRY_COLOR }),
      )
      entry.position.copy(pts[0])
      content.add(entry)
      const el = label(`${r.shipment_id} entry`, 'graph3d-label graph3d-entry')
      el.position.copy(pts[0]).add(new THREE.Vector3(0, 0.7, 0))
      content.add(el)

      // Sink node (yellow cone at the top of destination hub)
      const sinkPos = at(hub, snap.hours)
      const sink = new THREE.Mesh(
        new THREE.ConeGeometry(0.4, 0.8, 4),
        new THREE.MeshLambertMaterial({ color: '#FFD166' }),
      )
      sink.position.copy(sinkPos)
      content.add(sink)

      // Dashed line from last arrival to sink
      const sinkEdge = new THREE.LineSegments(
        new THREE.BufferGeometry().setFromPoints([pts[pts.length - 1], sinkPos]),
        new THREE.LineBasicMaterial({ color: '#FFD166', transparent: true, opacity: 0.5 }),
      )
      content.add(sinkEdge)

      const sl = label(`${hub} sink`, 'graph3d-label graph3d-sink')
      sl.position.copy(sinkPos).add(new THREE.Vector3(0, 0.8, 0))
      content.add(sl)
    }

    setLayers(layers)
    select(null)
  }

  function setCamera(preset: CameraPreset) {
    cameraGoal = new THREE.Vector3(...CAMERA_POSES[preset])
    controls.target.set(0, preset === 'top' ? 0 : TIME_HEIGHT / 2.5, 0)
  }

  function dispose() {
    cancelAnimationFrame(frame)
    ro.disconnect()
    renderer.domElement.removeEventListener('pointerdown', onDown)
    renderer.domElement.removeEventListener('pointerup', onUp)
    controls.dispose()
    disposeTree(scene)
    renderer.dispose()
    renderer.domElement.remove()
    labels.domElement.remove()
  }

  return { update, setLayers, setCamera, select, dispose }
}
