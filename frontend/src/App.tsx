import { useRef, useState } from 'react';
import {
  Activity,
  ArrowDownUp,
  ArrowRight,
  Check,
  ChevronDown,
  Clock3,
  Download,
  FileClock,
  Globe2,
  Info,
  Layers3,
  Radio,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Timer,
  WifiOff,
} from 'lucide-react';
import { object, type Observation } from './api';
import { milliseconds, remainingSeconds, utc } from './format';
import { useExchange } from './useExchange';
import PacketDiagram from './PacketDiagram';

const tabs = [
  { label: 'Real NTP Exchange', short: 'Exchange', icon: Globe2 },
  {
    label: 'Network Delay & Accuracy',
    short: 'Network Delay',
    icon: ArrowDownUp,
  },
  { label: 'Clock Synchronization', short: 'Synchronization', icon: Clock3 },
];
export function SourceBadge({ observation }: { observation: Observation | null }) {
  if (!observation)
    return (
      <span className="source-badge neutral">
        <span className="badge-dot" />
        Awaiting an exchange
      </span>
    );
  return (
    <span className={`source-badge ${observation.source}`}>
      {observation.source === 'replay' ? (
        <FileClock size={13} aria-hidden="true" />
      ) : (
        <Radio size={13} aria-hidden="true" />
      )}
      {observation.source === 'replay' ? 'REPLAY · original LIVE' : 'LIVE MEASUREMENT'}
    </span>
  );
}
function download(observation: Observation) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(observation.original, null, 2) + '\n'], {
      type: 'application/json',
    }),
  );
  const link = document.createElement('a');
  link.href = url;
  link.download = `ntp-${observation.source}-${observation.exchange.result_id}.json`;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function Details({ observation }: { observation: Observation }) {
  const { exchange } = observation;
  const data = exchange.data;
  const quartet = [
    data.timestamps.t1_unix_ns,
    data.timestamps.t2_unix_ns,
    data.timestamps.t3_unix_ns,
    data.timestamps.t4_unix_ns,
  ];
  const events = [
    'Client transmission',
    'Server reception',
    'Server transmission',
    'Client reception',
  ];
  return (
    <div className="details-stack">
      <details className="detail-section">
        <summary>
          <span>
            <Clock3 size={17} aria-hidden="true" />
            Four timestamps
          </span>
          <span className="summary-caption">
            UTC & exact nanoseconds <ChevronDown size={15} aria-hidden="true" />
          </span>
        </summary>
        <div className="timestamp-table-scroll">
          <table>
            <caption className="sr-only">Captured timestamps and clock ownership</caption>
            <thead>
              <tr>
                <th>Event</th>
                <th>Clock</th>
                <th>Captured time</th>
              </tr>
            </thead>
            <tbody>
              {quartet.map((time, i) => (
                <tr key={i}>
                  <th scope="row">
                    <span className="table-token">T{i + 1}</span>
                    {events[i]}
                  </th>
                  <td>{i === 0 || i === 3 ? 'Client' : 'Server'}</td>
                  <td>
                    <time>{utc(time)}</time>
                    <code>{time} ns</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="detail-note">
          Each clock owns its own timestamps. Comparing a server timestamp directly with a client
          timestamp does not establish event order.
        </p>
      </details>
      <details className="detail-section">
        <summary>
          <span>
            <Settings2 size={17} aria-hidden="true" />
            How the estimate works
          </span>
          <span className="summary-caption">
            Formula & substitution <ChevronDown size={15} aria-hidden="true" />
          </span>
        </summary>
        <div className="formula-grid">
          <div>
            <span className="eyebrow">SERVER MINUS CLIENT</span>
            <p className="formula">θ̂ = ((T2 − T1) + (T3 − T4)) / 2</p>
            <p className="exact-formula">
              (({quartet[1]} − {quartet[0]}) + ({quartet[2]} − {quartet[3]})) / 2 ns
            </p>
            <p className="formula-result">= {milliseconds(data.estimated_offset_ns, true)} ms</p>
          </div>
          <div>
            <span className="eyebrow">NETWORK ROUND TRIP</span>
            <p className="formula">δ = (T4 − T1) − (T3 − T2)</p>
            <p className="exact-formula">
              {milliseconds(data.client_elapsed_ns)} ms client elapsed −{' '}
              {milliseconds(data.server_processing_ns)} ms server processing
            </p>
            <p className="formula-result">= {milliseconds(data.round_trip_delay_ns)} ms</p>
          </div>
        </div>
        <p className="detail-note">
          Values are calculated by the shared Python engine. Positive offset means the client is
          behind the server. Equal clock rates and a stable offset during the exchange are assumed.
        </p>
      </details>
      <details className="detail-section">
        <summary>
          <span>
            <ShieldCheck size={17} aria-hidden="true" />
            Provenance & limitations
          </span>
          <span className="summary-caption">
            Software timestamps <ChevronDown size={15} aria-hidden="true" />
          </span>
        </summary>
        <div className="provenance-details">
          <p>
            <strong>Original capture:</strong> {exchange.created_at_utc}
          </p>
          <p>
            <strong>Source:</strong>{' '}
            {String(exchange.provenance.description ?? 'Actual UDP exchange')}
          </p>
          {observation.source === 'replay' && (
            <p>
              This is an archived capture. No new NTP request was sent. The original recording and
              capture metadata are retained.
            </p>
          )}
          <ul>
            {exchange.assumptions.map((value) => (
              <li key={value}>{value}</li>
            ))}
            <li>True offset and estimation error are unknown. RTT is not an accuracy bound.</li>
            <li>
              Peer/originate correlation is not cryptographic authentication. Only the 48-byte NTPv4
              profile is supported.
            </li>
          </ul>
          <button className="text-button" onClick={() => download(observation)}>
            <Download size={15} aria-hidden="true" />
            Export original JSON
          </button>
        </div>
      </details>
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState(0);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const model = useExchange();
  const { observation, busy, error, config } = model;
  const remaining = remainingSeconds(model.due, model.now);
  const server = config?.servers.find((s) => s.id === model.serverId);
  const blocked = server?.cooldown.state === 'blocked';
  const data = observation?.exchange.data;
  const peer =
    observation && object(observation.exchange.provenance.peer)
      ? observation.exchange.provenance.peer
      : null;
  const header = data && object(data.server_header) ? data.server_header : null;
  const navigateTab = (index: number) => {
    setTab(index);
    tabRefs.current[index]?.focus();
  };
  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to experiment
      </a>
      <div className="app-window">
        <header className="browser-chrome">
          <div className="toolbar">
            <a
              className="brand"
              href="#"
              onClick={(event) => {
                event.preventDefault();
                setTab(0);
              }}
              aria-label="NTP Sync Lab home"
            >
              <span className="brand-icon">
                <Clock3 size={21} strokeWidth={1.7} aria-hidden="true" />
              </span>
              <span>NTP Sync Lab</span>
            </a>
            <span className={`api-status ${config ? 'connected' : ''}`}>
              <span className="badge-dot" />
              {config
                ? 'API connected'
                : model.setupError
                  ? 'API unavailable'
                  : 'Connecting to API'}
            </span>
          </div>
          <nav className="tabs" role="tablist" aria-label="Experiments">
            {tabs.map((item, index) => (
              <button
                key={item.label}
                ref={(element) => {
                  tabRefs.current[index] = element;
                }}
                role="tab"
                id={`tab-${index}`}
                aria-controls={`panel-${index}`}
                aria-selected={tab === index}
                tabIndex={tab === index ? 0 : -1}
                onClick={() => setTab(index)}
                onKeyDown={(event) => {
                  if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
                    event.preventDefault();
                    navigateTab(
                      event.key === 'Home'
                        ? 0
                        : event.key === 'End'
                          ? 2
                          : (index + (event.key === 'ArrowRight' ? 1 : 2)) % 3,
                    );
                  }
                }}
              >
                <item.icon size={17} strokeWidth={1.6} aria-hidden="true" />
                <span className="tab-full">{item.label}</span>
                <span className="tab-short">{item.short}</span>
                {index > 0 && <span className="tab-coming">Soon</span>}
              </button>
            ))}
          </nav>
        </header>
        <main id="main-content">
          <div role="tabpanel" id="panel-0" aria-labelledby="tab-0" hidden={tab !== 0} tabIndex={0}>
            <div className="page-heading">
              <div>
                <p className="eyebrow">Experiment 01</p>
                <h1>Real NTP Exchange</h1>
                <p className="intro">See how two clocks estimate their time difference.</p>
              </div>
              <div className="heading-meta">
                <span className="scope-tag">
                  <ShieldCheck size={14} aria-hidden="true" />
                  Your system clock stays unchanged
                </span>
              </div>
            </div>
            {model.setupError && (
              <div className="alert" role="alert">
                <WifiOff size={19} aria-hidden="true" />
                <div>
                  <strong>Could not connect to the local API</strong>
                  <p>{model.setupError.message}</p>
                  <button className="text-button" onClick={() => void model.setup()}>
                    <RefreshCw size={14} aria-hidden="true" />
                    Reconnect
                  </button>
                </div>
              </div>
            )}
            <div className="workspace">
              <aside className="sidebar" aria-label="Exchange controls">
                <section className="control-panel glass">
                  <div className="section-heading">
                    <span className="section-icon">
                      <Settings2 size={17} aria-hidden="true" />
                    </span>
                    <h2>Exchange setup</h2>
                  </div>
                  <label className="field-label" htmlFor="server">
                    NTP server
                  </label>
                  <div className="select-shell">
                    <Globe2 size={16} aria-hidden="true" />
                    <select
                      id="server"
                      value={model.serverId}
                      disabled={!!busy || !config}
                      onChange={(e) => model.setServerId(e.target.value)}
                    >
                      {!config && <option>Waiting for API…</option>}
                      {config?.servers.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.hostname}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="timeout-row">
                    <label htmlFor="timeout">Response timeout</label>
                    <select
                      id="timeout"
                      value={model.timeout}
                      disabled={!!busy}
                      onChange={(e) => model.setTimeoutValue(Number(e.target.value))}
                    >
                      <option value="1">1 second</option>
                      <option value="3">3 seconds</option>
                      <option value="5">5 seconds</option>
                      <option value="10">10 seconds</option>
                    </select>
                  </div>
                  <button
                    className="primary-button"
                    disabled={
                      !config ||
                      !model.serverId ||
                      !!busy ||
                      config.live_busy ||
                      remaining > 0 ||
                      blocked
                    }
                    onClick={() => void model.execute('live')}
                  >
                    <Radio size={17} aria-hidden="true" />
                    {busy === 'live'
                      ? 'Measuring…'
                      : remaining > 0
                        ? `Available in ${remaining}s`
                        : blocked
                          ? 'Target blocked'
                          : config?.live_busy
                            ? 'Another measurement in progress'
                            : 'Measure once'}
                    {!busy && remaining === 0 && !blocked && (
                      <ArrowRight size={16} aria-hidden="true" />
                    )}
                  </button>
                  <p className="control-note">
                    One UDP request. No automatic polling. At least 64 seconds between requests to a
                    destination.
                  </p>
                  <p className="small-print">Timeout covers UDP. DNS may take longer.</p>
                  {config?.live_busy && !busy && (
                    <button className="text-button" onClick={() => void model.refresh()}>
                      <RefreshCw size={13} aria-hidden="true" />
                      Refresh availability
                    </button>
                  )}
                  {remaining > 0 && (
                    <p className="cooldown-note" role="status">
                      <Timer size={14} aria-hidden="true" />
                      Cooldown · {remaining}s remaining
                    </p>
                  )}
                  {blocked && (
                    <p className="cooldown-note">
                      Live polling is blocked: {server?.cooldown.code ?? 'state unavailable'}.
                      Review server policy; do not reset state.
                    </p>
                  )}
                  {server?.cooldown.state === 'unknown' && !remaining && (
                    <p className="small-print">
                      Cooldown will be checked by the server before sending.
                    </p>
                  )}
                  <div className="or-divider">
                    <span>or explore a real capture</span>
                  </div>
                  {model.recordings.length > 1 && (
                    <label className="field-label">
                      Saved capture
                      <select
                        aria-label="Saved capture"
                        value={model.recordingId}
                        onChange={(e) => model.setRecordingId(e.target.value)}
                        disabled={!!busy}
                      >
                        {model.recordings.map((r) => (
                          <option key={r.id} value={r.id}>
                            {r.id}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  <button
                    className="secondary-button"
                    disabled={!!busy || !model.recordingId}
                    onClick={() => void model.execute('replay')}
                  >
                    <FileClock size={17} aria-hidden="true" />
                    {busy === 'replay' ? 'Loading capture…' : 'Load captured exchange'}
                  </button>
                  <p className="control-note">
                    Previously recorded public NTP exchange.
                    <br />
                    Replay sends no new NTP request.
                  </p>
                </section>
                <section className="history-panel">
                  <div className="history-heading">
                    <h2>Session history</h2>
                    <span>
                      {model.history.length}
                      <span className="sr-only"> entries</span>
                    </span>
                  </div>
                  {model.history.length === 0 ? (
                    <div className="history-empty">
                      <Layers3 size={22} strokeWidth={1.3} aria-hidden="true" />
                      <p>Your exchanges will appear here.</p>
                      <span>Up to 20 entries · this session only</span>
                    </div>
                  ) : (
                    <ol className="history-list" aria-label="Session history">
                      {model.history.map((entry) => (
                        <li key={entry.key}>
                          <button
                            disabled={!!busy}
                            aria-pressed={observation?.key === entry.key}
                            onClick={() => model.selectHistory(entry)}
                          >
                            <span className={`history-symbol ${entry.source}`}>
                              {entry.source === 'replay' ? (
                                <FileClock size={15} aria-hidden="true" />
                              ) : (
                                <Radio size={15} aria-hidden="true" />
                              )}
                            </span>
                            <span>
                              <strong>
                                {entry.source === 'replay' ? 'Archived replay' : 'Live measurement'}
                              </strong>
                              <span>
                                {milliseconds(entry.exchange.data.estimated_offset_ns, true)} ms ·{' '}
                                {entry.exchange.created_at_utc.slice(11, 19)} UTC
                              </span>
                            </span>
                            {entry.key === observation?.key && (
                              <Check size={14} aria-hidden="true" />
                            )}
                          </button>
                        </li>
                      ))}
                    </ol>
                  )}
                </section>
              </aside>
              <div className="results-column" aria-busy={!!busy}>
                {error && (
                  <div className="alert" role="alert">
                    <Info size={20} aria-hidden="true" />
                    <div>
                      <strong>
                        {error.code === 'NTP_TIMEOUT'
                          ? 'The server did not reply in time.'
                          : 'This attempt did not complete.'}
                      </strong>
                      <p>{error.message}</p>
                      <code>{error.code}</code>
                      <p>
                        No automatic retry or fallback was made. Choose “Load captured exchange” to
                        explore a saved result.
                      </p>
                    </div>
                  </div>
                )}
                {error && observation && (
                  <p className="previous-result-note">
                    Showing the last selected successful result below, not a result of the failed
                    attempt.
                  </p>
                )}
                <div className="result-surface glass">
                  <div className="result-context">
                    <SourceBadge observation={observation} />
                    <span>
                      {observation
                        ? `${observation.source === 'replay' ? 'Captured' : 'Measured'} ${observation.exchange.created_at_utc.replace('T', ' ').replace('Z', ' UTC')}`
                        : 'Choose a live measurement or an archived capture'}
                    </span>
                  </div>
                  <PacketDiagram
                    key={observation?.key ?? 'empty'}
                    observation={observation}
                    active={tab === 0}
                  />
                  <div className="metrics" aria-label="Exchange results">
                    <div className="metric">
                      <span className="metric-label">
                        <Activity size={15} aria-hidden="true" />
                        Estimated offset
                      </span>
                      <p>
                        <span>{data ? milliseconds(data.estimated_offset_ns, true) : '—'}</span>
                        <span className="metric-unit">ms</span>
                      </p>
                      <span className="metric-caption">Server minus client</span>
                    </div>
                    <div className="metric">
                      <span className="metric-label">
                        <ArrowDownUp size={15} aria-hidden="true" />
                        Network round trip
                      </span>
                      <p>
                        <span>{data ? milliseconds(data.round_trip_delay_ns) : '—'}</span>
                        <span className="metric-unit">ms</span>
                      </p>
                      <span className="metric-caption">Server processing excluded</span>
                    </div>
                    <div className="metric unknown">
                      <span className="metric-label">
                        <ShieldCheck size={15} aria-hidden="true" />
                        Actual accuracy
                      </span>
                      <p>
                        <span>{data ? 'Unknown' : '—'}</span>
                      </p>
                      <span className="metric-caption">
                        True offset & estimation error unavailable
                      </span>
                    </div>
                  </div>
                  {observation ? (
                    <div className="conclusion">
                      <span className="conclusion-icon">
                        <Info size={16} aria-hidden="true" />
                      </span>
                      <p>
                        <strong>Reading the result.</strong> Positive offset means the client is
                        behind. Path asymmetry and software timestamps limit accuracy.
                      </p>
                    </div>
                  ) : (
                    <div className="empty-conclusion">
                      <Info size={15} aria-hidden="true" />
                      <span>
                        No measurement yet. Load the captured exchange for a fully offline
                        walkthrough.
                      </span>
                    </div>
                  )}
                </div>
                {observation && (
                  <>
                    <div className="protocol-line">
                      <span>
                        <span className="status-pin" />
                        {header
                          ? `NTPv${header.version} · mode ${header.mode} · stratum ${header.stratum} · ${header.packet_length} bytes`
                          : 'Validated NTP exchange'}
                      </span>
                      <span>
                        {peer
                          ? `${peer.address}:${peer.port}`
                          : String(observation.exchange.provenance.server ?? '')}
                        {observation.source === 'replay' && ' · historical peer'}
                      </span>
                    </div>
                    <Details observation={observation} />
                  </>
                )}
              </div>
            </div>
          </div>
          {[1, 2].map((index) => (
            <section
              key={index}
              role="tabpanel"
              id={`panel-${index}`}
              aria-labelledby={`tab-${index}`}
              hidden={tab !== index}
              tabIndex={0}
              className="coming-panel"
            >
              <div className="coming-icon">
                {index === 1 ? (
                  <ArrowDownUp size={34} strokeWidth={1.3} aria-hidden="true" />
                ) : (
                  <Clock3 size={34} strokeWidth={1.3} aria-hidden="true" />
                )}
              </div>
              <p className="eyebrow">EXPERIMENT 0{index + 1} · COMING LATER</p>
              <h1>{tabs[index].label}</h1>
              <p>This experiment’s web interface is not implemented in P3.2.</p>
              <button className="secondary-button" onClick={() => navigateTab(0)}>
                Back to Real NTP Exchange
                <ArrowRight size={16} aria-hidden="true" />
              </button>
            </section>
          ))}
        </main>
        <footer className="app-footer">
          <span>
            <Clock3 size={14} aria-hidden="true" />
            NTP Sync Lab <span className="footer-separator">/</span> An educational networking lab
          </span>
          <span>Calculated by the Python NTP engine</span>
        </footer>
      </div>
    </>
  );
}
