import type { CarResult } from '../types';

const priceFormatter = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });
const runFormatter = new Intl.NumberFormat('ru-RU');

function formatPrice(value: number): string {
  return `${priceFormatter.format(value)} ₽`;
}

function formatRun(value: number | null): string {
  if (value == null) return '—';
  return `${runFormatter.format(value)} км`;
}

export function CarCard({ car }: { car: CarResult }) {
  const { discounts } = car;
  const hasDiscount = discounts.max_discount > 0;

  const discountParts: string[] = [];
  if (discounts.tradein_discount > 0) {
    discountParts.push(`−${formatPrice(discounts.tradein_discount)} трейд-ин`);
  }
  if (discounts.credit_discount > 0) {
    discountParts.push(`−${formatPrice(discounts.credit_discount)} кредит`);
  }
  if (discounts.insurance_discount > 0) {
    discountParts.push(`−${formatPrice(discounts.insurance_discount)} страховка`);
  }

  const title = [car.mark_id, car.folder_id].filter(Boolean).join(' ');
  const subtitle = [car.modification_id, car.complectation_name].filter(Boolean).join(' · ');
  const location = [car.city, car.poi_id].filter(Boolean).join(' · ');

  return (
    <article className="car-card">
      <div className="car-card__photo">
        {car.images.length > 0 ? (
          <img src={car.images[0]} alt={title} loading="lazy" />
        ) : (
          <div className="car-card__photo-placeholder">Нет фото</div>
        )}
      </div>

      <div className="car-card__body">
        <h3 className="car-card__title">{title}</h3>
        {subtitle && <div className="car-card__subtitle">{subtitle}</div>}

        <div className="car-card__price">
          {hasDiscount && <span className="car-card__price-original">{formatPrice(car.price)}</span>}
          <span className="car-card__price-final">{formatPrice(car.price_after_max_discount)}</span>
        </div>
        {discountParts.length > 0 && (
          <div className="car-card__discounts">{discountParts.join(' · ')}</div>
        )}

        <dl className="car-card__specs">
          <div>
            <dt>Год</dt>
            <dd>{car.year}</dd>
          </div>
          <div>
            <dt>Пробег</dt>
            <dd>{formatRun(car.run)}</dd>
          </div>
          {car.state && (
            <div>
              <dt>Состояние</dt>
              <dd>{car.state}</dd>
            </div>
          )}
          {car.body_type && (
            <div>
              <dt>Кузов</dt>
              <dd>{car.body_type}</dd>
            </div>
          )}
          {car.transmission_type && (
            <div>
              <dt>КПП</dt>
              <dd>{car.transmission_type}</dd>
            </div>
          )}
          {car.drive_type && (
            <div>
              <dt>Привод</dt>
              <dd>{car.drive_type}</dd>
            </div>
          )}
          {car.owners_number && (
            <div>
              <dt>Владельцы</dt>
              <dd>{car.owners_number}</dd>
            </div>
          )}
        </dl>

        {location && <div className="car-card__location">{location}</div>}

        {car.url && (
          <a className="car-card__link" href={car.url} target="_blank" rel="noreferrer">
            Смотреть на сайте →
          </a>
        )}

        <p className="car-card__explanation">{car.explanation}</p>
      </div>
    </article>
  );
}
