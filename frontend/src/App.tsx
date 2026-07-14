import { useEffect, useState, type FormEvent, type KeyboardEvent } from 'react';
import { fetchCities, fetchStats, searchCars } from './api';
import { CarCard } from './components/CarCard';
import { ChatWidget } from './components/ChatWidget';
import { ComparisonTable } from './components/ComparisonTable';
import { ParsedFilterChips } from './components/ParsedFilterChips';
import type { CarResult, SearchResponse } from './types';

const SUGGESTIONS = [
  'Семье с двумя детьми, до 2.5 млн, чтобы надёжно и просторно',
  'Kia Rio, автомат, до 1 млн',
  'Кроссовер с полным приводом для зимы',
];

const MAX_COMPARE = 4;

export default function App() {
  const [cities, setCities] = useState<string[]>([]);
  const [city, setCity] = useState('');
  const [totalCars, setTotalCars] = useState<number | null>(null);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [conversation, setConversation] = useState<string[]>([]);
  const [refinement, setRefinement] = useState('');
  const [compareIds, setCompareIds] = useState<Set<string>>(new Set());
  const [showComparison, setShowComparison] = useState(false);

  useEffect(() => {
    fetchCities()
      .then(setCities)
      .catch(() => setCities([]));
  }, []);

  useEffect(() => {
    fetchStats(city || null)
      .then((stats) => setTotalCars(stats.total_cars))
      .catch(() => setTotalCars(null));
  }, [city]);

  async function runSearch(text: string) {
    if (!text.trim() || loading) return;

    setLoading(true);
    setError(null);
    setHasSearched(true);
    setCompareIds(new Set());
    setShowComparison(false);
    try {
      const result = await searchCars(text.trim(), city || null);
      setResponse(result);
      setConversation([text.trim()]);
    } catch (err) {
      setResponse(null);
      setError(err instanceof Error ? err.message : 'Что-то пошло не так');
    } finally {
      setLoading(false);
    }
  }

  async function runRefine(text: string) {
    if (!text.trim() || loading || !response) return;

    setLoading(true);
    setError(null);
    try {
      const result = await searchCars(text.trim(), city || null, response.parsed_filter);
      setResponse(result);
      setConversation((prev) => [...prev, text.trim()]);
      setRefinement('');
    } catch (err) {
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

  function handleRefineSubmit(event: FormEvent) {
    event.preventDefault();
    runRefine(refinement);
  }

  function toggleCompare(id: string) {
    setCompareIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else if (next.size < MAX_COMPARE) {
        next.add(id);
      }
      return next;
    });
  }

  const comparisonCars: CarResult[] =
    response?.results.filter((c) => compareIds.has(c.unique_id)) ?? [];

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
          Живой каталог: {totalCars != null ? <strong>{totalCars}</strong> : '…'} автомобилей в
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

        {conversation.length > 1 && (
          <div className="conversation-trail">
            {conversation.map((step, i) => (
              <span key={i} className="conversation-trail__item">
                {i === 0 ? step : `→ ${step}`}
              </span>
            ))}
          </div>
        )}

        {response && !loading && !error && <ParsedFilterChips filter={response.parsed_filter} />}

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
          <>
            <div className="results-toolbar">
              <span className="results-toolbar__count">
                Найдено подходящих: {response.results.length}
              </span>
              {compareIds.size >= 2 && (
                <button
                  type="button"
                  className="results-toolbar__compare-button"
                  onClick={() => setShowComparison(true)}
                >
                  Сравнить ({compareIds.size}) →
                </button>
              )}
            </div>

            <div className="results">
              {response.results.map((car) => (
                <CarCard
                  key={car.unique_id}
                  car={car}
                  compareChecked={compareIds.has(car.unique_id)}
                  onToggleCompare={() => toggleCompare(car.unique_id)}
                  compareDisabled={compareIds.size >= MAX_COMPARE}
                />
              ))}
            </div>

            <form className="refine-bar" onSubmit={handleRefineSubmit}>
              <input
                type="text"
                className="refine-bar__input"
                placeholder='Уточните: например, "а подешевле?" или "только с автоматом"'
                value={refinement}
                onChange={(e) => setRefinement(e.target.value)}
                aria-label="Уточнение запроса"
              />
              <button type="submit" className="refine-bar__button" disabled={loading}>
                {loading ? '…' : 'Уточнить'}
              </button>
            </form>
          </>
        )}
      </section>

      {showComparison && comparisonCars.length >= 2 && (
        <ComparisonTable cars={comparisonCars} onClose={() => setShowComparison(false)} />
      )}

      <ChatWidget />
    </div>
  );
}
