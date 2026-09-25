import clsx from 'clsx';
import type { ButtonHTMLAttributes, ReactNode } from 'react';

export function Section({
  title,
  children,
  className,
}: {
  title?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={clsx('rounded-2xl bg-section p-4 shadow-[0_1px_0_var(--app-line)]', className)}
    >
      {title && (
        <h2 className="mb-3 text-[13px] font-semibold uppercase tracking-wide text-hint">
          {title}
        </h2>
      )}
      {children}
    </section>
  );
}

export function Button({
  variant = 'primary',
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'ghost' | 'soft' }) {
  return (
    <button
      type="button"
      {...props}
      className={clsx(
        'pressable inline-flex h-11 items-center justify-center gap-2 rounded-xl px-4 text-[15px] font-semibold disabled:opacity-50',
        variant === 'primary' && 'bg-button text-button-fg',
        variant === 'soft' && 'bg-button/12 text-accent',
        variant === 'ghost' && 'text-link',
        className,
      )}
    />
  );
}

export function QuantityStepper({
  value,
  onInc,
  onDec,
  max,
  size = 'md',
  label,
}: {
  value: number;
  onInc: () => void;
  onDec: () => void;
  max?: number;
  size?: 'sm' | 'md';
  label?: string;
}) {
  const btn = clsx(
    'pressable grid place-items-center rounded-full bg-button/12 text-accent font-bold disabled:opacity-40',
    size === 'sm' ? 'size-8 text-lg' : 'size-10 text-xl',
  );
  return (
    <div className="inline-flex items-center gap-2" role="group" aria-label={label}>
      <button type="button" className={btn} onClick={onDec} aria-label="−">
        −
      </button>
      <span className="min-w-6 text-center font-semibold tabular-nums" aria-live="polite">
        {value}
      </span>
      <button
        type="button"
        className={btn}
        onClick={onInc}
        disabled={max !== undefined && value >= max}
        aria-label="+"
      >
        +
      </button>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  hint,
  action,
}: {
  icon: ReactNode;
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center px-8 py-16 text-center">
      <div className="mb-4 grid size-20 place-items-center rounded-full bg-section text-4xl">
        {icon}
      </div>
      <p className="text-lg font-semibold">{title}</p>
      {hint && <p className="mt-1 text-sm text-hint">{hint}</p>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx('animate-pulse rounded-2xl bg-section', className)} />;
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  name,
}: {
  value: T;
  options: { value: T; label: ReactNode }[];
  onChange: (v: T) => void;
  name: string;
}) {
  return (
    <div
      className="grid auto-cols-fr grid-flow-col gap-1 rounded-xl bg-page p-1"
      role="radiogroup"
      aria-label={name}
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={clsx(
            'h-10 rounded-lg text-sm font-semibold transition-colors',
            o.value === value ? 'bg-section text-fg shadow-sm' : 'text-hint',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
