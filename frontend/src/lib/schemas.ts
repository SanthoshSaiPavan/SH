import { z } from 'zod'

export const PrioritySchema = z.enum(['critical', 'high', 'medium', 'low'])
export type Priority = z.infer<typeof PrioritySchema>
export const StrategyTypeSchema = z.enum(['piggyback', 'reroute', 'dedicated', 'hold'])
export type StrategyType = z.infer<typeof StrategyTypeSchema>

export const HubSchema = z.object({
  id: z.string(), name: z.string(), city: z.string(), state: z.string(),
  lat: z.number(), lng: z.number(), hub_type: z.string(),
  capacity_packages: z.number(), current_load: z.number(),
})
export type Hub = z.infer<typeof HubSchema>

export const LiveStateSchema = z.object({
  vehicle_id: z.string(), lat: z.number(), lng: z.number(),
  speed: z.number(), heading: z.number(), timestamp: z.string(),
  status: z.string().optional(), connection: z.string().optional(),
  used_capacity_kg: z.number().optional(), max_capacity_kg: z.number().optional(),
  planned_route: z.array(z.string()).optional(), next_hub_id: z.string().nullable().optional(),
}).loose()
export type LiveState = z.infer<typeof LiveStateSchema>

export const VehicleSchema = z.object({
  id: z.string(), vehicle_type: z.string(), carrier_name: z.string(),
  current_lat: z.number(), current_lng: z.number(), route_id: z.string().nullable(),
  planned_route: z.array(z.string()), current_stop_index: z.number(),
  total_capacity_kg: z.number(), used_capacity_kg: z.number(),
  total_capacity_cbm: z.number(), used_capacity_cbm: z.number(),
  speed_kmh: z.number(), status: z.string(),
  piggybacked_shipments: z.array(z.string()), hazmat_certifications: z.array(z.string()),
  fleet_id: z.string(), live: LiveStateSchema.nullable(),
})
export type Vehicle = z.infer<typeof VehicleSchema>

export const ShipmentSchema = z.object({
  id: z.string(), tracking_number: z.string(), origin_hub_id: z.string(),
  destination_hub_id: z.string(), current_hub_id: z.string().nullable(),
  expected_route: z.array(z.string()), actual_route: z.array(z.string()).nullable(),
  status: z.string(), priority: PrioritySchema, handling_flags: z.array(z.string()),
  weight_kg: z.number(), volume_cbm: z.number(), deadline: z.string(),
  current_lat: z.number().nullable(), current_lng: z.number().nullable(),
  current_vehicle_id: z.string().nullable(), misplacement_type: z.string().nullable(),
  misplacement_detected_at: z.string().nullable(), recovery_strategy: z.string().nullable(),
  recovery_vehicle_id: z.string().nullable(), recovery_score: z.number().nullable(),
  recovery_mode: z.string().nullable(),
}).loose()
export type Shipment = z.infer<typeof ShipmentSchema>

export const LegSchema = z.object({
  vehicle_id: z.string(), from_hub: z.string(), to_hub: z.string(),
  departure_time: z.string(), arrival_time: z.string(), km: z.number(),
  remaining_kg: z.number(), total_kg: z.number(),
}).loose()
export type Leg = z.infer<typeof LegSchema>

export const StrategySchema = z.object({
  id: z.string(), type: StrategyTypeSchema, feasible: z.boolean(), cost: z.number(),
  arrival_time: z.string().nullable(), duration_hours: z.number(), distance_km: z.number(),
  detour_km: z.number(), vehicle_id: z.string().nullable(), hubs: z.array(z.string()),
  legs: z.array(LegSchema), deadline_met: z.boolean(), buffer_hours: z.number(),
  details: z.record(z.string(), z.unknown()), scores: z.record(z.string(), z.number()),
  score: z.number(),
})
export type Strategy = z.infer<typeof StrategySchema>

export const CandidateSchema = z.object({
  vehicle_id: z.string(), vehicles: z.array(z.string()), hubs: z.array(z.string()),
  score: z.number(), cost: z.number(), detour_km: z.number(), transfers: z.number(),
  first_hop_wait_hours: z.number(), pickup_time: z.string().nullable(),
  arrival_time: z.string(), available_capacity_kg: z.number(),
  scores: z.record(z.string(), z.number()),
}).loose()
export type Candidate = z.infer<typeof CandidateSchema>

export const EvaluationSchema = z.object({
  shipment_id: z.string(), recovery_mode: z.string(), recommended: StrategySchema.nullable(),
  recommendation_reason: z.string().nullable().optional(),
  strategies: z.array(StrategySchema), piggyback_candidates: z.array(CandidateSchema),
  dedicated_cost: z.number(), evaluated_at: z.string(),
  weights: z.record(z.string(), z.number()), piggyback_weights: z.record(z.string(), z.number()),
})
export type Evaluation = z.infer<typeof EvaluationSchema>

export const RecommendationSchema = z.object({
  shipment_id: z.string(), strategy: StrategyTypeSchema, strategy_id: z.string(),
  vehicle_id: z.string().nullable(), score: z.number(), pickup_eta: z.string().nullable().optional(),
  delivery_eta: z.string().nullable(), available_capacity: z.number().nullable().optional(),
  recovery_cost: z.number(), cost_saving: z.number(), recovery_mode: z.string(),
  deadline_met: z.boolean(), reason: z.string().nullable(),
})
export type Recommendation = z.infer<typeof RecommendationSchema>

export const ActionSchema = z.object({
  id: z.string(), shipment_id: z.string(), action_type: StrategyTypeSchema,
  matched_vehicle_id: z.string().nullable(),
  recovery_route: z.object({ hubs: z.array(z.string()).optional() }).loose().nullable(),
  additional_cost: z.number().nullable(), overall_score: z.number(), status: z.string(),
  created_at: z.string().nullable(), completed_at: z.string().nullable(),
}).loose()
export type RecoveryAction = z.infer<typeof ActionSchema>

export const DashboardSchema = z.object({
  active_shipments: z.number(), misplaced_now: z.number(), misplaced_today: z.number(),
  piggybacked_now: z.number(), recovery_rate: z.number().nullable(),
  recoveries_in_progress: z.number(), cost_saved_today: z.number(), cost_saved_total: z.number(),
})
export type Dashboard = z.infer<typeof DashboardSchema>

export const SimStatusSchema = z.object({
  mode: z.enum(['demo', 'live']), running: z.boolean(), speed: z.number(),
  tick_number: z.number(), auto_recovery: z.boolean(), sim_time: z.string(),
  available_speeds: z.array(z.number()),
})
export type SimStatus = z.infer<typeof SimStatusSchema>

export const AlertSchema = z.object({
  shipment_id: z.string(), type: z.string(), severity: z.string(),
  message: z.string(), priority: z.string().optional(), severity_score: z.number().optional(),
})
export type Alert = z.infer<typeof AlertSchema> & { at: number }

// ---- Time-expanded graph snapshot (GET /api/graph) ----
export const GraphNodeSchema = z.object({
  id: z.string(), kind: z.enum(['hub', 'arr', 'dep']), hub: z.string(), t: z.number(),
  vehicle_id: z.string().optional(), variant: z.string().optional(),
  remaining_kg: z.number().optional(), total_kg: z.number().optional(),
})
export type GraphNode = z.infer<typeof GraphNodeSchema>

export const GraphSnapshotSchema = z.object({
  now: z.string(), hours: z.number(), route_id: z.string().nullable(),
  hubs: z.array(z.object({ id: z.string(), name: z.string(), lat: z.number(), lng: z.number() })),
  nodes: z.array(GraphNodeSchema),
  edges: z.array(z.object({
    source: z.string(), target: z.string(), kind: z.string(),
    vehicle_id: z.string().optional(), km: z.number().optional(), detour: z.boolean().optional(),
  })),
  recommendations: z.array(z.object({
    shipment_id: z.string(), hub: z.string().nullable(), t: z.number(),
    legs: z.array(z.object({ vehicle_id: z.string(), from_hub: z.string(), to_hub: z.string(), dep_t: z.number(), arr_t: z.number() })),
  })),
})
export type GraphSnapshot = z.infer<typeof GraphSnapshotSchema>
