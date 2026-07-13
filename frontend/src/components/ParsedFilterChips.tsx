import type { CarFilter } from '../types';

function formatMoney(value: number): string {
  if (value >= 1_000_000) {
    const millions = value / 1_000_000;
    // 3000000 -> "3 млн", 1500000 -> "1.5 млн"
    const text = Number.isInteger(millions) ? String(millions) : millions.toFixed(1);
    return `${text} млн`;
  }
  if (value >= 1_000) {
    return `${Math.round(value / 1_000)} тыс`;
  }
  return `${value} ₽`;
}

const DRIVE_LABELS: Record<string, string> = {
  '4WD': 'полный привод',
  AWD: 'полный привод',
  FWD: 'передний привод',
};

/** Turns the structured filter the AI extracted into human-readable chips,
 * so the client literally sees the "translation" step happen and can spot
 * a misread. Order roughly mirrors how people phrase a request. */
function filterToChips(f: CarFilter): string[] {
  const chips: string[] = [];

  if (f.mark_id) chips.push(f.mark_id);
  if (f.body_type) chips.push(f.body_type.toLowerCase());
  if (f.family_friendly) chips.push('семейный (5+ мест)');
  if (f.drive_type) chips.push(DRIVE_LABELS[f.drive_type] ?? f.drive_type);
  if (f.transmission_type) chips.push(f.transmission_type);
  if (f.economical) chips.push('экономичный (двигатель ≤ 1.6 л)');

  if (f.price_min != null && f.price_max != null) {
    chips.push(`${formatMoney(f.price_min)} – ${formatMoney(f.price_max)}`);
  } else if (f.price_max != null) {
    chips.push(`до ${formatMoney(f.price_max)}`);
  } else if (f.price_min != null) {
    chips.push(`от ${formatMoney(f.price_min)}`);
  }

  if (f.year_min != null && f.year_max != null && f.year_min === f.year_max) {
    chips.push(`${f.year_min} г.`);
  } else {
    if (f.year_min != null) chips.push(`от ${f.year_min} г.`);
    if (f.year_max != null) chips.push(`до ${f.year_max} г.`);
  }

  if (f.run_max != null) chips.push(`пробег до ${new Intl.NumberFormat('ru-RU').format(f.run_max)} км`);
  if (f.doors_count != null) chips.push(`${f.doors_count} дв.`);
  if (f.owners_count_max != null) chips.push(`до ${f.owners_count_max} владельцев`);

  return chips;
}

export function ParsedFilterChips({ filter }: { filter: CarFilter }) {
  const chips = filterToChips(filter);
  const fuzzy = filter.free_text_intent?.trim();

  if (chips.length === 0 && !fuzzy) return null;

  return (
    <div className="parsed-filter">
      <span className="parsed-filter__label">Понял так:</span>
      <div className="parsed-filter__chips">
        {chips.map((c) => (
          <span key={c} className="parsed-filter__chip">
            {c}
          </span>
        ))}
        {fuzzy && (
          <span className="parsed-filter__chip parsed-filter__chip--fuzzy" title="Учитывается при ранжировании по смыслу">
            по смыслу: {fuzzy}
          </span>
        )}
      </div>
    </div>
  );
}
