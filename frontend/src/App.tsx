import { useEffect, useState, type FormEvent } from 'react';
import { fetchCities, searchCars } from './api';
import { CarCard } from './components/CarCard';
import type { SearchResponse } from './types';

export default function App() {
  const [cities, setCities] = useState<string[]>([]);
  const [city, setCity] = useState('');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  useEffect(() => {
    fetchCities()
      .then(setCities)
      .catch(() => setCities([]));
  }, []);

  async function handleSearch(event: FormEvent) {
    event.preventDefault();
    if (!query.trim() || loading) return;

    setLoading(true);
    setError(null);
    setHasSearched(true);
    try {
      const result = await searchCars(query.trim(), city || null);
      setResponse(result);
    } catch (err) {
      setResponse(null);
      setError(err instanceof Error ? err.message : 'Что-то пошло не так');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page">
      <header className="page__header">
        <h1>Подбор авто — демо</h1>
        <p className="page__subtitle">Опишите, какая машина нужна, своими словами</p>
      </header>

      <form className="search-bar" onSubmit={handleSearch}>
        <select
          className="search-bar__city"
          value={city}
          onChange={(e) => setCity(e.target.value)}
          aria-label="Город"
        >
          <option value="">Все города</option>
          {cities.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>

        <input
          type="text"
          className="search-bar__query"
          placeholder='например: "семейный кроссовер до 1.5 млн, автомат, не старше 2020"'
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Запрос"
        />

        <button type="submit" className="search-bar__button" disabled={loading}>
          {loading ? 'Ищем…' : 'Найти'}
        </button>
      </form>

      {error && <p className="state-message state-message--error">{error}</p>}

      {hasSearched && !loading && !error && response?.results.length === 0 && (
        <p className="state-message">Пока нет результатов, попробуйте изменить запрос.</p>
      )}

      {response && response.results.length > 0 && (
        <div className="results">
          {response.results.map((car) => (
            <CarCard key={car.unique_id} car={car} />
          ))}
        </div>
      )}
    </div>
  );
}
