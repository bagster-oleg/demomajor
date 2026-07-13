import { useEffect, useRef, useState, type FormEvent } from 'react';
import { searchCars } from '../api';
import type { CarFilter, CarResult } from '../types';

type ChatMessage =
  | { role: 'bot'; text: string }
  | { role: 'user'; text: string }
  | { role: 'results'; cars: CarResult[] };

const GREETING: ChatMessage = {
  role: 'bot',
  text: 'Здравствуйте! Опишите словами, какая машина нужна — например, «семейный кроссовер до 2 млн, автомат». Подберу из наличия.',
};

const priceFmt = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });
const money = (v: number) => `${priceFmt.format(v)} ₽`;

function CompactCar({ car }: { car: CarResult }) {
  return (
    <div className="cw-car">
      {car.images[0] ? (
        <img className="cw-car__photo" src={car.images[0]} alt="" loading="lazy" />
      ) : (
        <div className="cw-car__photo cw-car__photo--empty" />
      )}
      <div className="cw-car__body">
        <div className="cw-car__title">
          {car.mark_id} {car.folder_id}
        </div>
        <div className="cw-car__price">
          {money(car.price_after_max_discount)}
          {car.year ? ` · ${car.year}` : ''}
        </div>
        <div className="cw-car__explanation">{car.explanation}</div>
        {car.url && (
          <a className="cw-car__link" href={car.url} target="_blank" rel="noreferrer">
            Открыть карточку →
          </a>
        )}
      </div>
    </div>
  );
}

export function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([GREETING]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [lastFilter, setLastFilter] = useState<CarFilter | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading, open]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    setMessages((prev) => [...prev, { role: 'user', text: trimmed }]);
    setInput('');
    setLoading(true);
    try {
      const res = await searchCars(trimmed, null, lastFilter);
      setLastFilter(res.parsed_filter);

      if (res.results.length === 0) {
        setMessages((prev) => [
          ...prev,
          { role: 'bot', text: 'Пока ничего подходящего не нашёл. Попробуйте изменить запрос.' },
        ]);
      } else {
        const intro = res.exact_match
          ? `Нашёл ${res.results.length} ${plural(res.results.length)}:`
          : `Точного совпадения нет${
              res.relaxed_fields.length ? ` (без учёта: ${res.relaxed_fields.join(', ')})` : ''
            }, но есть похожие:`;
        setMessages((prev) => [
          ...prev,
          { role: 'bot', text: intro },
          { role: 'results', cars: res.results },
          { role: 'bot', text: 'Можно уточнить — например, «а подешевле» или «только полный привод».' },
        ]);
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: 'bot', text: 'Что-то пошло не так, попробуйте ещё раз.' },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    send(input);
  }

  return (
    <>
      {!open && (
        <button type="button" className="cw-fab" onClick={() => setOpen(true)}>
          <span className="cw-fab__icon">🚗</span>
          AI-подбор авто
        </button>
      )}

      {open && (
        <div className="cw-panel" role="dialog" aria-label="AI-подбор авто">
          <div className="cw-header">
            <div className="cw-header__title">
              <span className="cw-header__dot" />
              AI-подбор авто · Major
            </div>
            <button
              type="button"
              className="cw-header__close"
              onClick={() => setOpen(false)}
              aria-label="Свернуть"
            >
              ✕
            </button>
          </div>

          <div className="cw-messages" ref={scrollRef}>
            {messages.map((m, i) => {
              if (m.role === 'results') {
                return (
                  <div key={i} className="cw-results">
                    {m.cars.map((car) => (
                      <CompactCar key={car.unique_id} car={car} />
                    ))}
                  </div>
                );
              }
              return (
                <div key={i} className={`cw-msg cw-msg--${m.role}`}>
                  {m.text}
                </div>
              );
            })}
            {loading && <div className="cw-msg cw-msg--bot cw-msg--typing">Подбираю…</div>}
          </div>

          <form className="cw-input" onSubmit={handleSubmit}>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Опишите, какая машина нужна…"
              aria-label="Сообщение"
            />
            <button type="submit" disabled={loading} aria-label="Отправить">
              →
            </button>
          </form>
        </div>
      )}
    </>
  );
}

function plural(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'вариант';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return 'варианта';
  return 'вариантов';
}
