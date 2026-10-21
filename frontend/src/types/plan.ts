// 与后端 python/models/schemas.py 对应的 TypeScript 类型定义

export type TravelStyle =
  | "budget"
  | "comfort"
  | "luxury"
  | "adventure"
  | "cultural"
  | "relaxation";

export type PlanningState =
  | "collecting_preferences"
  | "recommending_destinations"
  | "searching_parallel"
  | "budget_checking"
  | "adjusting"
  | "completed"
  | "failed";

export interface UserPreferences {
  budget: number;
  travel_style: TravelStyle;
  departure_city: string;
  start_date: string;
  end_date: string;
  num_travelers: number;
  interests: string[];
  dietary_restrictions: string[];
  accessibility_needs: string[];
  notes: string;
  destination?: string | null;
}

export interface Destination {
  city: string;
  country: string;
  description: string;
  best_season: string;
  visa_required: boolean;
  safety_score: number;
  cost_level: string;
  highlights: string[];
}

export interface DestinationRecommendation {
  destinations: Destination[];
  selected: Destination | null;
  reasoning: string;
}

export interface Flight {
  airline: string;
  flight_no: string;
  departure_city: string;
  arrival_city: string;
  departure_time: string;
  arrival_time: string;
  price: number;
  duration_hours: number;
  stops: number;
  cabin_class: string;
}

export interface FlightSearchResult {
  outbound_flights: Flight[];
  return_flights: Flight[];
  recommended_outbound: Flight | null;
  recommended_return: Flight | null;
  total_flight_cost: number;
}

export interface Hotel {
  name: string;
  city: string;
  address: string;
  star_rating: number;
  user_rating: number;
  price_per_night: number;
  amenities: string[];
  distance_to_center_km: number;
}

export interface HotelSearchResult {
  hotels: Hotel[];
  recommended: Hotel | null;
  total_nights: number;
  total_hotel_cost: number;
}

export interface Activity {
  name: string;
  category: string;
  location: string;
  duration_hours: number;
  price: number;
  rating: number;
  description: string;
  time_slot: string;
}

export interface DayPlan {
  date: string;
  activities: Activity[];
  day_cost: number;
}

export interface ActivitySearchResult {
  day_plans: DayPlan[];
  total_activity_cost: number;
}

export interface BudgetBreakdown {
  flight_cost: number;
  hotel_cost: number;
  activity_cost: number;
  total_cost: number;
  budget: number;
  remaining: number;
  is_within_budget: boolean;
  over_budget_amount: number;
  suggestions: string[];
}

export interface TravelPlanState {
  state: PlanningState;
  preferences: UserPreferences | null;
  destination_rec: DestinationRecommendation | null;
  flight_result: FlightSearchResult | null;
  hotel_result: HotelSearchResult | null;
  activity_result: ActivitySearchResult | null;
  budget_breakdown: BudgetBreakdown | null;
  adjustment_round: number;
  max_adjustments: number;
  rag_context: string[];
  error_messages: string[];
}

export interface PlanRequest {
  budget: number;
  departure_city: string;
  start_date: string;
  end_date: string;
  travel_style: TravelStyle;
  num_travelers: number;
  interests: string[];
  notes: string;
  destination?: string | null;
}