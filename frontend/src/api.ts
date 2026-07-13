import type { SearchResponse, StatsResponse } from './types';

// Empty by default: in production the SPA and API share the same origin
// (nginx proxies /api/ to the backend on major.aifield.ru). Set
// VITE_API_BASE_URL only for local dev against a backend on another port.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '';

export async function fetchCities(): Promise<string[]> {
  const res = await fetch(`${API_BASE}/api/cities`);
  if (!res.ok) {
    throw new Error(`Не удалось загрузить список городов (${res.status})`);
  }
  return res.json();
}

export async function fetchStats(city: string | null): Promise<StatsResponse> {
  const params = city ? `?city=${encodeURIComponent(city)}` : '';
  const res = await fetch(`${API_BASE}/api/stats${params}`);
  if (!res.ok) {
    throw new Error(`Не удалось загрузить статистику (${res.status})`);
  }
  return res.json();
}

export async function searchCars(
  query: string,
  city: string | null,
  limit = 3,
): Promise<SearchResponse> {
  const res = await fetch(`${API_BASE}/api/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, city: city || undefined, limit }),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Поиск не удался (${res.status}): ${text || 'нет ответа от сервера'}`);
  }
  return res.json();
}
