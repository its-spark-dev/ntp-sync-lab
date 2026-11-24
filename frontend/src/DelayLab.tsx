import { useState } from 'react';
import { ArrowRight, Settings2 } from 'lucide-react';
import { milliseconds } from './format';
import {
  simulateDelay,
  type DelayResult,
  type DelaySeries,
  type DelayInput,
} from './simulationApi';
import {
  ComparisonChart,
  DecimalField,
  defaults,
  EmptySimulation,
  Metric,
  ModelContext,
  ModelDetails,
  presets,
  ResetButton,
  SimulationError,
  SimulationHeader,
  useSimulation,
} from './SimulationShared';

type Mode = 'single' | 'equal' | 'fixed';
export default function DelayLab() {
  const model = useSimulation<DelayResult | DelaySeries>();
  const [fields, setFields] = useState({ ...defaults });
  const [preset, setPreset] = useState('symmetric-low');
  const [mode, setMode] = useState<Mode>('single');
  const [total, setTotal] = useState('80');
  const [points, setPoints] = useState(3);
  const [selected, setSelected] = useState(0);
  const [submitted, setSubmitted] = useState('');
  const request: DelayInput =
    mode === 'fixed'
      ? {
          true_offset_ms: fields.true_offset_ms,
          processing_ms: fields.processing_ms,
          round_trip_ms: total,
          sweep_points: points,
        }
      : mode === 'equal'
        ? { ...fields, increments_ms: ['0', '60'] }
        : { ...fields };
  const dirty = !!model.result && submitted !== JSON.stringify(request);
  const results = model.result
    ? 'points' in model.result.data
      ? (model.result as DelaySeries).data.points
      : [model.result as DelayResult]
    : [];
  const inspected = results[Math.min(selected, results.length - 1)];
  const data = inspected?.data;
  const change = (key: keyof typeof fields, value: string) => {
    setFields((previous) => ({ ...previous, [key]: value }));
    setPreset('custom');
  };
  return (
    <>
      <SimulationHeader number={2} title="Network Delay & Accuracy">
        Compare known clock offset with the estimate from different network paths.
      </SimulationHeader>
      <div className="workspace simulation-workspace">
        <aside className="sidebar" aria-label="Delay controls">
          <form
            className="control-panel"
            onSubmit={(e) => {
              e.preventDefault();
              const snapshot = JSON.stringify(request);
              void model.execute(async () => {
                const result = await simulateDelay(request);
                setSubmitted(snapshot);
                setSelected(0);
                return result;
              });
            }}
          >
            <div className="section-heading">
              <Settings2 size={18} aria-hidden="true" />
              <h2>Delay setup</h2>
            </div>
            <label className="simulation-field">
              <span>Comparison</span>
              <select
                value={mode}
                disabled={model.busy}
                onChange={(e) => setMode(e.target.value as Mode)}
              >
                <option value="single">Single exchange</option>
                <option value="equal">Increase both delays</option>
                <option value="fixed">Fixed RTT asymmetry</option>
              </select>
            </label>
            {mode !== 'fixed' && (
              <label className="simulation-field">
                <span>Delay preset</span>
                <select
                  value={preset}
                  disabled={model.busy}
                  onChange={(e) => {
                    setPreset(e.target.value);
                    const item = presets.find((v) => v.id === e.target.value);
                    if (item)
                      setFields({
                        ...defaults,
                        forward_ms: item.forward_ms,
                        reverse_ms: item.reverse_ms,
                      });
                  }}
                >
                  {presets.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                  <option value="custom">Custom</option>
                </select>
              </label>
            )}
            <button className="primary-button" disabled={model.busy}>
              {model.busy ? 'Calculating…' : 'Run delay simulation'}
              <ArrowRight size={16} aria-hidden="true" />
            </button>
            <DecimalField
              label="True offset · server minus client"
              value={fields.true_offset_ms}
              signed
              disabled={model.busy}
              onChange={(v) => change('true_offset_ms', v)}
            />
            {mode === 'fixed' ? (
              <>
                <DecimalField
                  label="Fixed network RTT"
                  value={total}
                  onChange={setTotal}
                  disabled={model.busy}
                />
                <label className="simulation-field">
                  <span>Comparison points</span>
                  <select
                    value={points}
                    disabled={model.busy}
                    onChange={(e) => setPoints(Number(e.target.value))}
                  >
                    {[3, 5, 9].map((v) => (
                      <option key={v} value={v}>
                        {v} points
                      </option>
                    ))}
                  </select>
                </label>
              </>
            ) : (
              <>
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
              </>
            )}
            <DecimalField
              label="Server processing"
              value={fields.processing_ms}
              onChange={(v) => change('processing_ms', v)}
              disabled={model.busy}
            />
            {mode === 'equal' && (
              <p className="control-note">
                Compares the base path with +60 ms added to each direction. Both conditions are
                calculated by Python.
              </p>
            )}
            {mode === 'fixed' && (
              <p className="control-note">
                Sweeps from all-reverse to all-forward delay, while keeping the requested RTT fixed.
              </p>
            )}

            <p className="control-note">
              Ideal equal-rate clocks. These controls model delays; they do not alter a public
              network.
            </p>
            <ResetButton
              disabled={model.busy}
              onClick={() => {
                model.reset();
                setFields({ ...defaults });
                setPreset('symmetric-low');
                setMode('single');
                setTotal('80');
                setPoints(3);
                setSelected(0);
                setSubmitted('');
              }}
            />
          </form>
        </aside>
        <div className="results-column" aria-busy={model.busy}>
          <SimulationError error={model.error} hasResult={!!model.result} />
          {dirty && (
            <p className="input-change-note" role="status">
              Inputs changed. Run the simulation to update the results below.
            </p>
          )}
          <section className="result-surface" aria-label="Delay simulation results">
            <ModelContext
              created={model.result?.created_at_utc}
              description="Known truth · controlled one-way delays"
            />
            <div className="metrics">
              <Metric
                label="True offset"
                value={data?.true_offset_ns ?? undefined}
                caption="Server minus client · known model truth"
                signed
              />
              <Metric
                label="Estimated offset"
                value={data?.estimated_offset_ns}
                caption="Four-timestamp estimate from Python"
                signed
              />
              <Metric
                label="Estimation error"
                value={data?.estimation_error_ns ?? undefined}
                caption="Estimate minus true offset"
                signed
              />
            </div>
            {data ? (
              <div className="simulation-content">
                <div className="simulation-section-heading">
                  <h2>True and estimated time</h2>
                  <span className="small-tag">
                    Network RTT <strong>{milliseconds(data.round_trip_delay_ns)} ms</strong>
                  </span>
                </div>
                <ComparisonChart
                  values={[
                    { label: 'True offset', ns: data.true_offset_ns!, style: 'truth' },
                    { label: 'NTP estimate', ns: data.estimated_offset_ns, style: 'estimate' },
                    { label: 'Estimation error', ns: data.estimation_error_ns!, style: 'error' },
                  ]}
                />
                <p className="run-conditions">
                  Selected path: {milliseconds(String(data.forward_delay_ns))} ms forward /{' '}
                  {milliseconds(String(data.reverse_delay_ns))} ms reverse. Processing:{' '}
                  {milliseconds(data.server_processing_ns)} ms.
                </p>
                {results.length > 1 && (
                  <div className="series-table-scroll">
                    <table className="series-table">
                      <caption>
                        Comparison · select a point to inspect its timestamps and metrics
                      </caption>
                      <thead>
                        <tr>
                          <th>Point</th>
                          <th>Forward / reverse</th>
                          <th>RTT</th>
                          <th>Estimate</th>
                          <th>Error</th>
                        </tr>
                      </thead>
                      <tbody>
                        {results.map((r, i) => (
                          <tr key={r.result_id} aria-selected={selected === i}>
                            <th scope="row">
                              <label>
                                <input
                                  type="radio"
                                  name="delay-point"
                                  checked={selected === i}
                                  onChange={() => setSelected(i)}
                                />
                                Point {i + 1}
                              </label>
                            </th>
                            <td>
                              {milliseconds(String(r.data.forward_delay_ns))} /{' '}
                              {milliseconds(String(r.data.reverse_delay_ns))} ms
                            </td>
                            <td>{milliseconds(r.data.round_trip_delay_ns)} ms</td>
                            <td>{milliseconds(r.data.estimated_offset_ns, true)} ms</td>
                            <td>{milliseconds(r.data.estimation_error_ns!, true)} ms</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ) : (
              <EmptySimulation>
                Choose a path and run the simulation. The model returns known truth, an NTP
                estimate, and the difference between them.
              </EmptySimulation>
            )}
            {data && (
              <div className="conclusion">
                <p>
                  <strong>What this shows.</strong>{' '}
                  {String(data.conclusion).replace(/[.!?]?$/, '.')} Offset bias is (forward −
                  reverse delay) / 2. RTT alone does not determine accuracy.
                </p>
              </div>
            )}
          </section>
          {inspected && (
            <ModelDetails
              key={inspected.result_id}
              result={inspected}
              exportDocument={model.result ?? undefined}
            />
          )}
        </div>
      </div>
    </>
  );
}
