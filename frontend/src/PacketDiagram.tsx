import { useEffect, useState } from 'react';
import { Pause, Play, RotateCcw, SkipForward } from 'lucide-react';
import type { Observation } from './api';
import { utc } from './format';

export function useReducedMotion() {
  const [reduced, setReduced] = useState(
    () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  return reduced;
}
const eventDescriptions = [
  'Ready to trace the exchange',
  'T1 · Client sends a request',
  'T2 · Server receives the request',
  'T3 · Server sends its response',
  'T4 · Client receives the response',
];

export default function PacketDiagram({
  observation,
  active,
}: {
  observation: Observation | null;
  active: boolean;
}) {
  const [stage, setStage] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const reduced = useReducedMotion();
  useEffect(() => {
    if (!active || reduced) setPlaying(false);
  }, [active, reduced]);
  useEffect(() => {
    if (!playing) return;
    if (stage === 4) {
      setPlaying(false);
      return;
    }
    const timer = window.setTimeout(() => setStage((s) => s + 1), 950 / speed);
    return () => window.clearTimeout(timer);
  }, [playing, stage, speed]);
  const timestamps = observation?.exchange.data.timestamps;
  const times = timestamps
    ? [timestamps.t1_unix_ns, timestamps.t2_unix_ns, timestamps.t3_unix_ns, timestamps.t4_unix_ns]
    : [];
  const timeLabel = (i: number) =>
    times[i]
      ? utc(times[i]).split(' ')[1].slice(0, 12) + ' UTC'
      : ['Request sent', 'Request received', 'Response sent', 'Response received'][i];
  return (
    <section className="exchange-panel" aria-labelledby="exchange-title">
      <div className="panel-heading">
        <div>
          <h2 id="exchange-title">The packet exchange</h2>
        </div>
        <span className="small-tag">NTPv4 · UDP</span>
      </div>
      <div className="diagram-wrap">
        <svg
          className="packet-diagram"
          viewBox="0 0 760 342"
          role="img"
          aria-labelledby="diagram-title diagram-description"
        >
          <title id="diagram-title">Client and server exchange diagram</title>
          <desc id="diagram-description">
            T1 and T4 use the client clock. T2 and T3 use the server clock. The arrows illustrate
            event order, not measured one-way transit time or synchronized clock positions.
          </desc>
          <defs>
            <linearGradient id="request-gradient">
              <stop stopColor="#2c6dec" />
              <stop offset="1" stopColor="#8faee6" />
            </linearGradient>
            <linearGradient id="response-gradient">
              <stop stopColor="#8b9dcc" />
              <stop offset="1" stopColor="#535cd9" />
            </linearGradient>
            <marker
              id="arrow-blue"
              markerWidth="8"
              markerHeight="8"
              refX="6"
              refY="4"
              orient="auto"
            >
              <path d="M1 1 L6 4 L1 7" fill="none" stroke="#4079df" strokeWidth="1.4" />
            </marker>
            <marker
              id="arrow-purple"
              markerWidth="8"
              markerHeight="8"
              refX="6"
              refY="4"
              orient="auto"
            >
              <path d="M1 1 L6 4 L1 7" fill="none" stroke="#6c6fbd" strokeWidth="1.4" />
            </marker>
          </defs>
          <rect x="110" y="13" width="100" height="38" rx="19" className="diagram-pill" />
          <rect x="550" y="13" width="100" height="38" rx="19" className="diagram-pill" />
          <text x="160" y="37" textAnchor="middle" className="lane-heading">
            Client
          </text>
          <text x="600" y="37" textAnchor="middle" className="lane-heading">
            Server
          </text>
          <text x="160" y="70" textAnchor="middle" className="lane-caption">
            your clock
          </text>
          <text x="600" y="70" textAnchor="middle" className="lane-caption">
            reference clock
          </text>
          <line x1="160" y1="87" x2="160" y2="315" className="clock-lane" />
          <line x1="600" y1="87" x2="600" y2="315" className="clock-lane" />
          <path
            d="M170 114 L587 169"
            className={`packet-path request-path ${stage >= 2 ? 'traced' : ''}`}
            markerEnd="url(#arrow-blue)"
          />
          <path
            d="M590 227 L173 282"
            className={`packet-path response-path ${stage >= 4 ? 'traced' : ''}`}
            markerEnd="url(#arrow-purple)"
          />
          <g className="path-label">
            <rect x="314" y="116" width="132" height="28" rx="14" />
            <text x="380" y="135" textAnchor="middle">
              Client request →
            </text>
          </g>
          <g className="path-label return">
            <rect x="308" y="229" width="144" height="28" rx="14" />
            <text x="380" y="248" textAnchor="middle">
              ← Server response
            </text>
          </g>
          {[
            [160, 114],
            [600, 170],
            [600, 226],
            [160, 282],
          ].map(([x, y], i) => (
            <g
              key={i}
              className={`timestamp-node ${stage === i + 1 ? 'current' : ''} ${stage >= i + 1 ? 'visited' : ''}`}
            >
              <circle cx={x} cy={y} r="10" className="node-halo" />
              <circle cx={x} cy={y} r="4.5" className="node-dot" />
              <text
                x={i === 0 || i === 3 ? x - 22 : x + 22}
                y={y - 4}
                textAnchor={i === 0 || i === 3 ? 'end' : 'start'}
                className="node-name"
              >
                T{i + 1}
              </text>
              <text
                x={i === 0 || i === 3 ? x - 22 : x + 22}
                y={y + 15}
                textAnchor={i === 0 || i === 3 ? 'end' : 'start'}
                className="node-time"
              >
                {timeLabel(i)}
              </text>
            </g>
          ))}
          <line x1="614" y1="186" x2="614" y2="210" stroke="#9ca9bd" strokeWidth="1.5" />
          <text x="635" y="202" className="lane-caption">
            processing
          </text>
        </svg>
      </div>
      <div className="playback-strip">
        <div className="playback-buttons">
          <button
            className="icon-button"
            aria-label="Restart illustration"
            disabled={!observation}
            onClick={() => {
              setStage(0);
              setPlaying(false);
            }}
          >
            <RotateCcw size={16} aria-hidden="true" />
          </button>
          <button
            className="play-button"
            disabled={!observation}
            onClick={() => {
              if (reduced) setStage((s) => (s >= 4 ? 1 : s + 1));
              else {
                if (stage === 4) setStage(0);
                setPlaying((p) => !p);
              }
            }}
            aria-label={
              reduced ? 'Next event' : playing ? 'Pause illustration' : 'Play exchange illustration'
            }
          >
            {reduced ? (
              <SkipForward size={15} aria-hidden="true" />
            ) : playing ? (
              <Pause size={15} aria-hidden="true" />
            ) : (
              <Play size={15} fill="currentColor" aria-hidden="true" />
            )}
            <span>{reduced ? 'Next event' : playing ? 'Pause' : 'Play exchange'}</span>
          </button>
          <label className="speed-label">
            <span className="sr-only">Playback speed</span>
            <select
              aria-label="Playback speed"
              value={speed}
              disabled={reduced || !observation}
              onChange={(e) => setSpeed(Number(e.target.value))}
            >
              <option value="0.5">0.5×</option>
              <option value="1">1×</option>
              <option value="2">2×</option>
            </select>
          </label>
        </div>
        <span className="playback-status" role="status">
          {eventDescriptions[stage]}
        </span>
      </div>
      <p className="diagram-note">
        Illustrative playback · Arrow lengths and animation speed do not represent actual one-way
        delays.
        {' Diagram labels show milliseconds; exact nanoseconds are in Four timestamps.'}
        {reduced && ' Reduced motion: advance one event at a time.'}
      </p>
    </section>
  );
}
