import { ChevronDown, Clock3, Download, Info, RotateCcw, ShieldCheck } from 'lucide-react';
import { useRef, useState } from 'react';
import { ApiError } from './api';
import { milliseconds, utc } from './format';
import type { DelayResult, DelaySeries, SyncResult } from './simulationApi';

// Inputs stay strings until the Python boundary. No local NTP estimator or correction math.
export const defaults = {
  true_offset_ms: '100',
  forward_ms: '20',
  reverse_ms: '20',
  processing_ms: '5',
};
export const presets = [
  { id: 'symmetric-low', label: 'Symmetric · 20 / 20 ms', forward_ms: '20', reverse_ms: '20' },
  { id: 'symmetric-high', label: 'Symmetric · 80 / 80 ms', forward_ms: '80', reverse_ms: '80' },
  {
    id: 'asymmetric-forward',
    label: 'Asymmetric · 60 / 20 ms',
    forward_ms: '60',
    reverse_ms: '20',
  },
  {
    id: 'asymmetric-reverse',
    label: 'Asymmetric · 20 / 60 ms',
    forward_ms: '20',
    reverse_ms: '60',
  },
];
export function useSimulation<T>() {
  const [result, setResult] = useState<T | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const lock = useRef(false);
  const execute = async (run: () => Promise<T>) => {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError(null);
    try {
      setResult(await run());
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e
          : new ApiError(
              'INVALID_RESULT',
              'The simulation response could not be displayed. No retry was made.',
            ),
      );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  return {
    result,
    busy,
    error,
    execute,
    reset: () => {
      if (!lock.current) {
        setResult(null);
        setError(null);
      }
    },
  };
}
export function SimulationHeader({
  number,
  title,
  children,
}: {
  number: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <p className="eyebrow">Experiment 0{number}</p>
        <h1>{title}</h1>
        <p className="intro">{children}</p>
      </div>
      <span className="scope-tag">
        <ShieldCheck size={14} aria-hidden="true" />
        Offline model · no NTP requests
      </span>
    </div>
  );
}
export function DecimalField({
  label,
  value,
  onChange,
  signed = false,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  signed?: boolean;
  disabled?: boolean;
}) {
  return (
    <label className="simulation-field">
      <span>{label}</span>
      <span className="decimal-input">
        <input
          type="text"
          inputMode={signed ? 'text' : 'decimal'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          maxLength={128}
          disabled={disabled}
          required
          pattern={signed ? '-?[0-9]+([.][0-9]{1,6})?' : '[0-9]+([.][0-9]{1,6})?'}
          autoComplete="off"
          spellCheck={false}
        />
        <span aria-hidden="true">ms</span>
      </span>
    </label>
  );
}
export function ResetButton({ onClick, disabled }: { onClick: () => void; disabled: boolean }) {
  return (
    <button
      type="button"
      className="text-button reset-button"
      disabled={disabled}
      onClick={onClick}
    >
      <RotateCcw size={15} aria-hidden="true" />
      Reset experiment
    </button>
  );
}
export function SimulationError({
  error,
  hasResult,
}: {
  error: ApiError | null;
  hasResult: boolean;
}) {
  return (
    error && (
      <div className="alert" role="alert">
        <Info size={20} aria-hidden="true" />
        <div>
          <strong>Simulation could not complete.</strong>
          <p>{error.message}</p>
          <code>{error.code}</code>
          {hasResult && (
            <p>
              Showing the previous successful run below. It does not represent the failed request.
            </p>
          )}
        </div>
      </div>
    )
  );
}
export function ModelContext({ created, description }: { created?: string; description: string }) {
  return (
    <div className="result-context">
      <span className="source-badge simulation">
        <ShieldCheck size={14} aria-hidden="true" />
        SIMULATION
      </span>
      <span>
        {created ? `Created ${created.replace('T', ' ').replace('Z', ' UTC')}` : description}
      </span>
    </div>
  );
}
export function Metric({
  label,
  value,
  caption,
  signed = false,
}: {
  label: string;
  value?: string;
  caption: string;
  signed?: boolean;
}) {
  return (
    <div className="metric">
      <span className="metric-label">{label}</span>
      <p>
        <span>{value === undefined ? '—' : milliseconds(value, signed)}</span>
        <span className="metric-unit">ms</span>
      </p>
      <span className="metric-caption">{caption}</span>
    </div>
  );
}
export function EmptySimulation({ children }: { children: React.ReactNode }) {
  return (
    <div className="simulation-empty">
      <Clock3 size={36} strokeWidth={1.3} aria-hidden="true" />
      <h2>Ready when you are.</h2>
      <p>{children}</p>
    </div>
  );
}
export function ModelDetails({
  result,
  extra,
  exportDocument,
}: {
  result: DelayResult | SyncResult;
  extra?: React.ReactNode;
  exportDocument?: DelayResult | DelaySeries | SyncResult;
}) {
  const data = result.data;
  const quartet = [
    data.timestamps.t1_unix_ns,
    data.timestamps.t2_unix_ns,
    data.timestamps.t3_unix_ns,
    data.timestamps.t4_unix_ns,
  ];
  const labels = [
    'Client transmission',
    'Server reception',
    'Server transmission',
    'Client reception',
  ];
  return (
    <div className="details-stack simulation-details">
      <details className="detail-section">
        <summary>
          <span>
            <Clock3 size={17} aria-hidden="true" />
            Modeled timestamps & calculations
          </span>
          <ChevronDown size={16} aria-hidden="true" />
        </summary>
        <div className="timestamp-table-scroll">
          <table>
            <caption className="sr-only">Modeled four timestamps</caption>
            <thead>
              <tr>
                <th>Event</th>
                <th>Clock</th>
                <th>Modeled time</th>
              </tr>
            </thead>
            <tbody>
              {quartet.map((t, i) => (
                <tr key={i}>
                  <th scope="row">
                    T{i + 1} · {labels[i]}
                  </th>
                  <td>{i === 0 || i === 3 ? 'Client' : 'Reference/server'}</td>
                  <td>
                    <time>{utc(t)}</time>
                    <code>{t} ns</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="formula-grid">
          <div>
            <p className="formula">θ̂ = ((T2 − T1) + (T3 − T4)) / 2</p>
            <p className="exact-formula">
              (({quartet[1]} − {quartet[0]}) + ({quartet[2]} − {quartet[3]})) / 2 ns
            </p>
            <p className="formula-result">= {milliseconds(data.estimated_offset_ns, true)} ms</p>
          </div>
          <div>
            <p className="formula">δ = (T4 − T1) − (T3 − T2)</p>
            <p className="exact-formula">
              {milliseconds(data.client_elapsed_ns)} ms elapsed −{' '}
              {milliseconds(data.server_processing_ns)} ms processing
            </p>
            <p className="formula-result">= {milliseconds(data.round_trip_delay_ns)} ms</p>
          </div>
        </div>
        <p className="detail-note">
          Offset means server minus client. Known truth exists in this model; it is unavailable for
          a public exchange. Calculations are returned by Python.
        </p>
      </details>
      {extra}
      <details className="detail-section">
        <summary>
          <span>
            <ShieldCheck size={17} aria-hidden="true" />
            Model assumptions & original JSON
          </span>
          <ChevronDown size={16} aria-hidden="true" />
        </summary>
        <div className="provenance-details">
          <ul>
            {result.assumptions.map((v) => (
              <li key={v}>{v}</li>
            ))}
          </ul>
          <p>
            Creation date: {result.created_at_utc}. The fixed modeled epoch is not a network capture
            date.
          </p>
          <button
            className="text-button"
            onClick={() => {
              const url = URL.createObjectURL(
                new Blob([JSON.stringify(exportDocument ?? result, null, 2) + '\n'], {
                  type: 'application/json',
                }),
              );
              const a = document.createElement('a');
              a.href = url;
              a.download = `ntp-simulation-${result.result_id}.json`;
              a.click();
              window.setTimeout(() => URL.revokeObjectURL(url), 1000);
            }}
          >
            <Download size={15} aria-hidden="true" />
            Export simulation JSON
          </button>
        </div>
      </details>
    </div>
  );
}
// Approximate chart geometry only; exact values and signs remain visible in the labels/table.
export function ComparisonChart({
  values,
}: {
  values: { label: string; ns: string; style: string }[];
}) {
  const max = Math.max(...values.map((v) => Math.abs(Number(v.ns))), 1);
  return (
    <div
      className="comparison-chart"
      role="img"
      aria-label={values
        .map((v) => `${v.label}: ${milliseconds(v.ns, true)} milliseconds`)
        .join('; ')}
    >
      <p className="chart-key">
        Negative <span>0 ms</span> Positive
      </p>
      {values.map((v) => (
        <div className="comparison-row" key={v.label}>
          <span>{v.label}</span>
          <div className="bar-track" aria-hidden="true">
            <span
              className={`value-bar ${v.style}`}
              style={{
                left: Number(v.ns) < 0 ? `${50 - (Math.abs(Number(v.ns)) / max) * 46}%` : '50%',
                width: Number(v.ns) === 0 ? '0' : `${(Math.abs(Number(v.ns)) / max) * 46}%`,
              }}
            />
            <span className="zero-line" />
          </div>
          <strong>{milliseconds(v.ns, true)} ms</strong>
        </div>
      ))}
      <p className="chart-note">
        Shared scale · exact values in ms · bar positions are illustrative
      </p>
    </div>
  );
}
