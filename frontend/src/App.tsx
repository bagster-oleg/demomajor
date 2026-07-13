import { useEffect, useState, type KeyboardEvent } from 'react';
import { fetchCities, fetchStats, searchCars } from './api';
import { CarCard } from './components/CarCard';
import type { SearchResponse } from './types';

const SUGGESTIONS = [
  'Семье с двумя детьми, до 2.5 млн, чтобы надёжно и просторно',
  'Kia Rio, автомат, до 1 млн',
  'Кроссовер с полным приводом для зимы',
];

export default function App() {
  const [cities, setCities] = useState<string[]>([]);
  const [city, setCity] = useState('');
  const [totalModels, setTotalModels] = useState<number | null>(null);
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

  useEffect(() => {
    fetchStats(city || null)
      .then((stats) => setTotalModels(stats.total_models))
      .catch(() => setTotalModels(null));
  }, [city]);

  async function runSearch(text: string) {
    if (!text.trim() || loading) return;

    setLoading(true);
    setError(null);
    setHasSearched(true);
    try {
      const result = await searchCars(text.trim(), city || null);
      setResponse(result);
    } catch (err) {
      setResponse(null);
      setError(err instanceof Error ? err.message : 'Что-то пошло не так');
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      runSearch(query);
    }
  }

  function handleSuggestionClick(text: string) {
    setQuery(text);
    runSearch(text);
  }

  return (
    <div className="app">
      <header className="site-header">
        <div className="site-header__inner">
          <div className="site-header__logo">
            MAJOR<span>.</span>
          </div>
          <div className="site-header__nav">ИИ-подбор автомобиля</div>
          <div className="site-header__badge">Demo</div>
        </div>
      </header>

      <main className="hero">
        <p className="hero__eyebrow">
          Подбор из наличия ·{' '}
          <select
            className="hero__city-select"
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
        </p>

        <h1 className="hero__title">
          Опишите словами, какая нужна машина — подберём из наличия Major
        </h1>

        <p className="hero__subtitle">
          Живой каталог: {totalModels != null ? <strong>{totalModels}</strong> : '…'} моделей в
          наличии. Укажите бюджет, задачи, семью — или сразу конкретную марку и модель, если
          знаете, что ищете. Отфильтруем точно по цифрам из наличия.
        </p>

        <form
          className="search-card"
          onSubmit={(e) => {
            e.preventDefault();
            runSearch(query);
          }}
        >
          <textarea
            className="search-card__input"
            placeholder='например: семейный кроссовер до 3 млн, полный привод, чтобы зимой уверенно и не жрал бензин'
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={3}
            aria-label="Запрос"
          />
          <div className="search-card__footer">
            <span className="search-card__hint">Enter — подобрать · Shift+Enter — новая строка</span>
            <button type="submit" className="search-card__button" disabled={loading}>
              {loading ? 'Ищем…' : <>Подобрать →</>}
            </button>
          </div>
        </form>

        <div className="suggestions">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              className="suggestion-chip"
              onClick={() => handleSuggestionClick(s)}
            >
              {s}
            </button>
          ))}
        </div>
      </main>

      <section className="results-section">
        {error && <p className="state-message state-message--error">{error}</p>}

        {hasSearched && !loading && !error && response?.results.length === 0 && (
          <p className="state-message">
            Ничего подходящего нет даже среди похожих вариантов — попробуйте изменить запрос.
          </p>
        )}

        {response && response.results.length > 0 && !response.exact_match && (
          <p className="state-message state-message--notice">
            Точного совпадения по всем условиям нет — показаны похожие варианты из наличия
            {response.relaxed_fields.length > 0 && (
              <>
                {' '}
                (без учёта: {response.relaxed_fields.join(', ')})
              </>
            )}
            .
          </p>
        )}

        {response && response.results.length > 0 && (
          <div className="results">
            {response.results.map((car) => (
              <CarCard key={car.unique_id} car={car} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
