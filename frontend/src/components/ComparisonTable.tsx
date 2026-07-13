import type { CarResult } from '../types';

const priceFormatter = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });
const runFormatter = new Intl.NumberFormat('ru-RU');

function formatPrice(value: number): string {
  return `${priceFormatter.format(value)} ₽`;
}

function formatRun(value: number | null): string {
  return value == null ? '—' : `${runFormatter.format(value)} км`;
}

/** Index of the "best" value in a column - lower price/mileage, higher
 * year - purely a deterministic min/max over real fields already shown on
 * the cards, no LLM judgement involved. */
function bestIndex(values: (number | null)[], mode: 'min' | 'max'): number | null {
  let bestIdx: number | null = null;
  let bestVal: number | null = null;
  values.forEach((v, i) => {
    if (v == null) return;
    if (bestVal == null || (mode === 'min' ? v < bestVal : v > bestVal)) {
      bestVal = v;
      bestIdx = i;
    }
  });
  return bestIdx;
}

interface Row {
  label: string;
  values: (string | number)[];
  bestIdx?: number | null;
}

export function ComparisonTable({
  cars,
  onClose,
}: {
  cars: CarResult[];
  onClose: () => void;
}) {
  const prices = cars.map((c) => c.price_after_max_discount);
  const runs = cars.map((c) => c.run);
  const years = cars.map((c) => c.year);

  const rows: Row[] = [
    {
      label: 'Цена',
      values: cars.map((c) => formatPrice(c.price_after_max_discount)),
      bestIdx: bestIndex(prices, 'min'),
    },
    { label: 'Год', values: years, bestIdx: bestIndex(years, 'max') },
    { label: 'Пробег', values: cars.map((c) => formatRun(c.run)), bestIdx: bestIndex(runs, 'min') },
    { label: 'Кузов', values: cars.map((c) => c.body_type ?? '—') },
    { label: 'КПП', values: cars.map((c) => c.transmission_type ?? '—') },
    { label: 'Привод', values: cars.map((c) => c.drive_type ?? '—') },
    { label: 'Цвет', values: cars.map((c) => c.color ?? '—') },
    { label: 'Дверей', values: cars.map((c) => c.doors_count ?? '—') },
    { label: 'Владельцы', values: cars.map((c) => c.owners_number ?? '—') },
    { label: 'Состояние', values: cars.map((c) => c.state ?? '—') },
    { label: 'Город', values: cars.map((c) => c.city) },
  ];

  return (
    <div className="comparison-overlay" role="dialog" aria-modal="true">
      <div className="comparison-panel">
        <div className="comparison-panel__header">
          <h2>Сравнение автомобилей</h2>
          <button
            type="button"
            className="comparison-panel__close"
            onClick={onClose}
            aria-label="Закрыть сравнение"
          >
            ✕
          </button>
        </div>

        <div className="comparison-scroll">
          <table className="comparison-table">
            <thead>
              <tr>
                <th />
                {cars.map((car) => (
                  <th key={car.unique_id}>
                    {car.images[0] ? (
                      <img className="comparison-table__photo" src={car.images[0]} alt="" />
                    ) : (
                      <div className="comparison-table__photo comparison-table__photo--empty" />
                    )}
                    <div className="comparison-table__title">
                      {car.mark_id} {car.folder_id}
                    </div>
                    {car.url && (
                      <a
                        className="comparison-table__link"
                        href={car.url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Смотреть →
                      </a>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.label}>
                  <th>{row.label}</th>
                  {row.values.map((value, i) => (
                    <td
                      key={i}
                      className={row.bestIdx === i ? 'comparison-table__best' : undefined}
                    >
                      {value}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
