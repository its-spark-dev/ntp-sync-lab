import { useState } from 'react';
import { ArrowRight, Check, ChevronDown, Clock3, Settings2 } from 'lucide-react';
import { milliseconds, utc } from './format';
import { simulateSync, type SyncInput, type SyncResult } from './simulationApi';
import {
  ComparisonChart,
  DecimalField,
  EmptySimulation,
  Metric,
  ModelContext,
  ModelDetails,
  ResetButton,
  SimulationError,
  SimulationHeader,
  useSimulation,
} from './SimulationShared';
const defaults = {
  client_offset_ms: '120',
  forward_ms: '20',
  reverse_ms: '20',
  processing_ms: '5',
};
const cases = [
  { id: 'symmetric', label: 'Symmetric · zero residual', ...defaults },
  { id: 'forward', label: 'Forward-heavy · positive residual', ...defaults, forward_ms: '60' },
  { id: 'reverse', label: 'Reverse-heavy · negative residual', ...defaults, reverse_ms: '60' },
  { id: 'behind', label: 'Client behind reference', ...defaults, client_offset_ms: '-120' },
  {
    id: 'aligned',
    label: 'Aligned client · asymmetric path',
    ...defaults,
    client_offset_ms: '0',
    forward_ms: '60',
  },
];
export default function SyncLab() {
  const model = useSimulation<SyncResult>();
  const [fields, setFields] = useState({ ...defaults });
  const [preset, setPreset] = useState('symmetric');
  const [submitted, setSubmitted] = useState('');
  const [applied, setApplied] = useState(false);
  const request: SyncInput = { ...fields, mode: 'step' };
  const dirty = !!model.result && submitted !== JSON.stringify(request);
  const data = model.result?.data;
  const change = (key: keyof typeof fields, value: string) => {
    setPreset('custom');
    setFields((previous) => ({ ...previous, [key]: value }));
  };
  return (
    <>
      <SimulationHeader number={3} title="Clock Synchronization">
        Measure a virtual clock, apply the estimated offset, and inspect the remaining error.
      </SimulationHeader>
      <div className="workspace simulation-workspace">
        <aside className="sidebar" aria-label="Virtual clock controls">
          <form
            className="control-panel"
            onSubmit={(e) => {
              e.preventDefault();
              const snapshot = JSON.stringify(request);
              void model.execute(async () => {
                const result = await simulateSync(request);
                setSubmitted(snapshot);
                setApplied(false);
                return result;
              });
            }}
          >
            <div className="section-heading">
              <Settings2 size={18} aria-hidden="true" />
              <h2>Virtual clock setup</h2>
            </div>
            <label className="simulation-field">
              <span>Clock scenario</span>
              <select
                value={preset}
                disabled={model.busy}
                onChange={(e) => {
                  setPreset(e.target.value);
                  const item = cases.find((c) => c.id === e.target.value);
                  if (item)
                    setFields({
                      client_offset_ms: item.client_offset_ms,
                      forward_ms: item.forward_ms,
                      reverse_ms: item.reverse_ms,
                      processing_ms: item.processing_ms,
                    });
                }}
              >
                {cases.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label}
                  </option>
                ))}
                <option value="custom">Custom</option>
              </select>
            </label>
            <button className="primary-button" disabled={model.busy}>
              {model.busy ? 'Measuring model…' : 'Measure virtual clock'}
              <ArrowRight size={16} aria-hidden="true" />
            </button>
            <DecimalField
              label="Initial error · client minus reference"
              value={fields.client_offset_ms}
              signed
              onChange={(v) => change('client_offset_ms', v)}
              disabled={model.busy}
            />
            <DecimalField
              label="Forward delay · client to server"
              value={fields.forward_ms}
              onChange={(v) => change('forward_ms', v)}
              disabled={model.busy}
            />
            <DecimalField
              label="Reverse delay · server to client"
              value={fields.reverse_ms}
              onChange={(v) => change('reverse_ms', v)}
              disabled={model.busy}
            />
            <DecimalField
              label="Server processing"
              value={fields.processing_ms}
              onChange={(v) => change('processing_ms', v)}
              disabled={model.busy}
            />

            <p className="control-note">
              Only a virtual clock changes. Equal clock rates, a single step, no drift or gradual
              correction.
            </p>
            <ResetButton
              disabled={model.busy}
              onClick={() => {
                model.reset();
                setFields({ ...defaults });
                setPreset('symmetric');
                setSubmitted('');
                setApplied(false);
              }}
            />
          </form>
        </aside>
        <div className="results-column" aria-busy={model.busy}>
          <SimulationError error={model.error} hasResult={!!model.result} />
          {dirty && (
            <p className="input-change-note" role="status">
              Inputs changed. Measure the virtual clock again before applying a correction.
            </p>
          )}
          <section className="result-surface" aria-label="Virtual clock results">
            <ModelContext
              created={model.result?.created_at_utc}
              description="Virtual time only · no operating-system clock change"
            />
            <div className="metrics">
              <Metric
                label="Initial client error"
                value={data?.initial_client_error_ns}
                caption="Client minus reference"
                signed
              />
              <Metric
                label="Estimated correction"
                value={data?.applied_correction_ns}
                caption="Reference minus client · add to virtual time"
                signed
              />
              {applied ? (
                <Metric
                  label="Residual client error"
                  value={data?.final_client_error_ns}
                  caption="Client minus reference after the step"
                  signed
                />
              ) : (
                <div className="metric pending-metric">
                  <span className="metric-label">Residual client error</span>
                  <p>
                    <span>{data ? 'Not applied' : '—'}</span>
                  </p>
                  <span className="metric-caption">
                    Apply the correction to reveal the residual
                  </span>
                </div>
              )}
            </div>
            {data ? (
              <div className="simulation-content">
                <div className="simulation-section-heading">
                  <h2>Virtual clock correction</h2>
                  <span className="small-tag">Step correction</span>
                </div>
                <p className="run-conditions">
                  Known NTP offset: {milliseconds(data.true_offset_ns!, true)} ms. Modeled path:{' '}
                  {milliseconds(String(model.result!.parameters.forward_delay_ns))} /{' '}
                  {milliseconds(String(model.result!.parameters.reverse_delay_ns))} ms.
                </p>
                <div className="clock-comparison">
                  <section className="clock-snapshot" aria-label="Before correction">
                    <Clock3 size={26} strokeWidth={1.5} aria-hidden="true" />
                    <h3>Before correction</h3>
                    <p className="clock-error">
                      {milliseconds(data.before.client_error_ns, true)} <span>ms</span>
                    </p>
                    <p>Client minus reference</p>
                  </section>
                  <ArrowRight className="snapshot-arrow" size={22} aria-hidden="true" />
                  <section
                    className={`clock-snapshot ${applied ? 'corrected' : ''}`}
                    aria-label="After correction"
                  >
                    {applied ? (
                      <Check size={26} aria-hidden="true" />
                    ) : (
                      <Clock3 size={26} strokeWidth={1.5} aria-hidden="true" />
                    )}
                    <h3>After correction</h3>
                    <p className="clock-error">
                      {applied ? (
                        <>
                          {milliseconds(data.after.client_error_ns, true)} <span>ms</span>
                        </>
                      ) : (
                        'Awaiting step'
                      )}
                    </p>
                    <p>
                      {applied
                        ? 'Client minus reference'
                        : 'Calculated by Python; reveal with Apply'}
                    </p>
                  </section>
                </div>
                <div className="apply-row">
                  <button
                    className="primary-button"
                    disabled={model.busy || dirty || applied || !!model.error}
                    onClick={() => setApplied(true)}
                  >
                    {applied ? (
                      <>
                        <Check size={17} aria-hidden="true" />
                        Correction applied
                      </>
                    ) : (
                      'Apply correction'
                    )}
                  </button>
                  <p role="status">
                    {applied
                      ? 'The backend-provided after snapshot is now shown. No OS clock changed.'
                      : 'Adds the estimated offset to virtual time. Negative corrections step backward.'}
                  </p>
                </div>
                {applied && (
                  <ComparisonChart
                    values={[
                      { label: 'Before error', ns: data.before.client_error_ns, style: 'truth' },
                      { label: 'Correction', ns: data.applied_correction_ns, style: 'estimate' },
                      { label: 'Residual error', ns: data.after.client_error_ns, style: 'error' },
                    ]}
                  />
                )}
                <p className="reference-instant">
                  Same reference instant: <time>{utc(data.before.reference_unix_ns)}</time>
                </p>
              </div>
            ) : (
              <EmptySimulation>
                Measure the modeled exchange first. Then apply its estimated correction to the same
                virtual clock.
              </EmptySimulation>
            )}
            {data && (
              <div className="conclusion">
                <p>
                  <strong>{applied ? 'After the step.' : 'Before the step.'}</strong>{' '}
                  {applied
                    ? data.conclusion
                    : 'Correction is ready. The residual is not yet shown; use Apply correction to inspect the backend’s after snapshot.'}
                </p>
              </div>
            )}
          </section>
          {model.result && (
            <ModelDetails
              result={model.result}
              extra={
                <details className="detail-section">
                  <summary>
                    <span>Virtual clock snapshots & timeline</span>
                    <ChevronDown size={16} aria-hidden="true" />
                  </summary>
                  <p className="detail-note">
                    Before and after share one reference instant. Snapshot readings retain exact
                    whole or half nanoseconds. Only the displayed stage changes when Apply is
                    pressed.
                  </p>
                  <div className="timestamp-table-scroll">
                    <table>
                      <caption className="sr-only">Backend virtual clock timeline</caption>
                      <thead>
                        <tr>
                          <th>Stage</th>
                          <th>Reference Unix ns</th>
                          <th>Virtual client Unix ns</th>
                          <th>Client error</th>
                        </tr>
                      </thead>
                      <tbody>
                        {model.result.data.timeline
                          .filter((p) => applied || p.sequence < 2)
                          .map((p) => (
                            <tr key={p.sequence}>
                              <th scope="row">{p.stage.replaceAll('_', ' ')}</th>
                              <td>
                                <code>{p.reference_unix_ns}</code>
                              </td>
                              <td>
                                <code>{p.virtual_client_unix_ns}</code>
                              </td>
                              <td>{milliseconds(p.client_error_ns, true)} ms</td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              }
            />
          )}
        </div>
      </div>
    </>
  );
}
