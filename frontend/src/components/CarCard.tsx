import { useState } from 'react';
import type { CarResult } from '../types';

const priceFormatter = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });
const runFormatter = new Intl.NumberFormat('ru-RU');
const MAX_EXTRAS_SHOWN = 6;

function formatPrice(value: number): string {
  return `${priceFormatter.format(value)} ₽`;
}

function formatRun(value: number | null): string {
  if (value == null) return '—';
  return `${runFormatter.format(value)} км`;
}

function PhotoGallery({ images, alt }: { images: string[]; alt: string }) {
  const [index, setIndex] = useState(0);

  if (images.length === 0) {
    return (
      <div className="car-card__photo">
        <div className="car-card__photo-placeholder">Нет фото</div>
      </div>
    );
  }

  function go(delta: number) {
    setIndex((i) => (i + delta + images.length) % images.length);
  }

  return (
    <div className="car-card__photo">
      <img src={images[index]} alt={alt} loading="lazy" />
      {images.length > 1 && (
        <>
          <button
            type="button"
            className="car-card__photo-nav car-card__photo-nav--prev"
            onClick={() => go(-1)}
            aria-label="Предыдущее фото"
          >
            ‹
          </button>
          <button
            type="button"
            className="car-card__photo-nav car-card__photo-nav--next"
            onClick={() => go(1)}
            aria-label="Следующее фото"
          >
            ›
          </button>
          <span className="car-card__photo-count">
            {index + 1} / {images.length}
          </span>
        </>
      )}
    </div>
  );
}

interface CarCardProps {
  car: CarResult;
  compareChecked?: boolean;
  onToggleCompare?: () => void;
  compareDisabled?: boolean;
}

export function CarCard({ car, compareChecked, onToggleCompare, compareDisabled }: CarCardProps) {
  const [showAllExtras, setShowAllExtras] = useState(false);
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

  const extrasList = (car.extras ?? '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  const visibleExtras = showAllExtras ? extrasList : extrasList.slice(0, MAX_EXTRAS_SHOWN);
  const hiddenExtrasCount = extrasList.length - visibleExtras.length;

  return (
    <article className="car-card">
      <PhotoGallery images={car.images} alt={title} />

      <div className="car-card__body">
        {onToggleCompare && (
          <label className="car-card__compare">
            <input
              type="checkbox"
              checked={compareChecked ?? false}
              disabled={compareDisabled && !compareChecked}
              onChange={onToggleCompare}
            />
            Сравнить
          </label>
        )}

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
          {car.color && (
            <div>
              <dt>Цвет</dt>
              <dd>{car.color}</dd>
            </div>
          )}
          {car.doors_count != null && (
            <div>
              <dt>Дверей</dt>
              <dd>{car.doors_count}</dd>
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
          {car.fuel_type && (
            <div>
              <dt>Тип двигателя</dt>
              <dd>{car.fuel_type}</dd>
            </div>
          )}
          {car.engine_volume_l != null && (
            <div>
              <dt>Двигатель</dt>
              <dd>
                {car.engine_volume_l} л{car.power_hp != null ? ` · ${car.power_hp} л.с.` : ''}
              </dd>
            </div>
          )}
          {car.seats != null && (
            <div>
              <dt>Мест</dt>
              <dd>{car.seats}</dd>
            </div>
          )}
          {car.owners_number && (
            <div>
              <dt>Владельцы</dt>
              <dd>{car.owners_number}</dd>
            </div>
          )}
          {car.custom && (
            <div>
              <dt>Таможня</dt>
              <dd>{car.custom}</dd>
            </div>
          )}
          {car.not_registered_in_russia && (
            <div>
              <dt>Регистрация</dt>
              <dd>не зарегистрирован в РФ</dd>
            </div>
          )}
        </dl>

        {extrasList.length > 0 && (
          <div className="car-card__extras">
            {visibleExtras.map((item) => (
              <span key={item} className="car-card__extra-tag">
                {item}
              </span>
            ))}
            {hiddenExtrasCount > 0 && (
              <button
                type="button"
                className="car-card__extra-tag car-card__extra-tag--more"
                onClick={() => setShowAllExtras(true)}
              >
                +{hiddenExtrasCount} ещё
              </button>
            )}
          </div>
        )}

        {location && <div className="car-card__location">{location}</div>}

        <div className="car-card__links">
          {car.url && (
            <a className="car-card__link" href={car.url} target="_blank" rel="noreferrer">
              Смотреть на сайте →
            </a>
          )}
          {car.video && (
            <a className="car-card__link" href={car.video} target="_blank" rel="noreferrer">
              Видеообзор →
            </a>
          )}
          {car.contact_phone && (
            <a className="car-card__link" href={`tel:${car.contact_phone}`}>
              {car.contact_phone}
              {car.contact_hours ? ` (${car.contact_hours})` : ''}
            </a>
          )}
        </div>

        <p className="car-card__explanation">{car.explanation}</p>
      </div>
    </article>
  );
}
