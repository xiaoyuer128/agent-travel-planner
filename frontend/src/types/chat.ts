export interface Preferences {
  departure_city?: string; destination?: string; budget?: number;
  num_travelers?: number; start_date?: string; days?: number; interests?: string[];
  pace?: string; transport?: string; walking?: string; needs?: string; selected_spots?: string[];
}
export interface Source { id: string; city: string; title: string; text: string; score: number; source: string; uri: string; version: string }
export interface Plan {
  version: number; mode: string; preferences: Required<Preferences>; sources: Source[];
  flights: {id: string; label: string; price_cents: number}[];
  hotel: {id: string; name: string; price_cents: number; stars: number};
  days: {day: number; date: string; title: string; description: string; source_ids: string[]; cost_per_person_cents: number}[];
  cost: {flight_cents: number; hotel_cents: number; activity_cents: number; total_cents: number; budget_cents: number; remaining_cents: number; within_budget: boolean; rooms: number; nights: number};
  warnings: string[]; changed_sections: string[];
}
export interface Session {
  provider?: string;
  id: string; title: string; revision: number; preferences: Preferences; plan: Plan | null;
  versions: Plan[]; messages: {role: 'user' | 'assistant'; content: string;sources?:Source[]}[]; trace: string[];
}
export interface SessionItem {id: string; title: string; revision: number; updated: string}
