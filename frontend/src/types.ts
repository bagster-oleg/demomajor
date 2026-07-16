export interface Discounts {
  max_discount: number;
  tradein_discount: number;
  credit_discount: number;
  insurance_discount: number;
}

export interface CarResult {
  id: number;
  unique_id: string;
  vin: string | null;
  mark_id: string;
  folder_id: string;
  modification_id: string | null;
  complectation_name: string | null;
  body_type: string | null;
  color: string | null;
  drive_type: string | null;
  transmission_type: string | null;
  doors_count: number | null;
  engine_volume_l: number | null;
  power_hp: number | null;
  seats: number | null;
  year: number;
  run: number | null;
  owners_number: string | null;
  state: string | null;
  custom: string | null;
  extras: string | null;
  price: number;
  currency: string | null;
  discounts: Discounts;
  price_after_max_discount: number;
  city: string;
  poi_id: string | null;
  contact_phone: string | null;
  contact_hours: string | null;
  images: string[];
  video: string | null;
  url: string | null;
  explanation: string;
}

export interface CarFilter {
  city: string | null;
  price_min: number | null;
  price_max: number | null;
  year_min: number | null;
  year_max: number | null;
  run_max: number | null;
  mark_id: string | null;
  body_type: string | null;
  color: string | null;
  drive_type: string | null;
  transmission_type: string | null;
  doors_count: number | null;
  owners_count_max: number | null;
  engine_volume_min: number | null;
  engine_volume_max: number | null;
  power_hp_min: number | null;
  power_hp_max: number | null;
  seats_min: number | null;
  family_friendly: boolean | null;
  economical: boolean | null;
  prefer_cheap: boolean | null;
  free_text_intent: string | null;
}

export interface SearchResponse {
  parsed_filter: CarFilter;
  city_used: string | null;
  total_candidates_after_sql_filter: number;
  exact_match: boolean;
  relaxed_fields: string[];
  results: CarResult[];
}

export interface StatsResponse {
  total_cars: number;
  total_models: number;
}
