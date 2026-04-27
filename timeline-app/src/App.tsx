import React, { useState, useEffect } from 'react';

type Track = {
  name: string;
  color: string;
  items: Clip[];
};

type Clip = {
  start: number;
  duration: number;
  label: string;
  file: string;
  color?: string;
};

type TimelineData = {
  project_id: string;
  meta: any;
  w24: any;
  receipt: any;
  transcript: { start: number; end: number; text: string }[];
  total_duration: number;
  tracks: Record<string, Clip[]>;
};

const TRACK_COLORS: Record<string, string> = {
  Video: '#4CAF50',
  VO: '#2196F3',
  'O-Ton': '#FF9800',
  Music: '#9C27B0',
  Subtitle: '#F44336',
};

const PX_PER_SEC = 40;

function formatTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
}

function Cursor({ time, height }: { time: number; height: number }) {
  const x = time * PX_PER_SEC + 140;
  return (
    <div
      style={{
        position: 'absolute',
        left: x,
        top: 0,
        height,
        width: 2,
        background: '#ff4444',
        pointerEvents: 'none',
        zIndex: 20,
      }}
    />
  );
}

function App() {
  const [data, setData] = useState<TimelineData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState('timeline');
  const [playTime, setPlayTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    fetch('/project.json')
      .then((r) => {
        if (!r.ok) throw new Error('No project.json');
        return r.json();
      })
      .then((meta) => {
        return fetch('/timeline_data.json')
          .then((r) => {
            if (!r.ok) throw new Error('No timeline_data.json');
            return r.json();
          })
          .then((tl) => ({ meta, tl }));
      })
      .then(({ meta, tl }) => {
        setData(tl as TimelineData);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!playing || !data) return;
    const interval = setInterval(() => {
      setPlayTime((t) => {
        if (t >= data.total_duration) {
          setPlaying(false);
          return data.total_duration;
        }
        return t + 0.1;
      });
    }, 100);
    return () => clearInterval(interval);
  }, [playing, data]);

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', fontSize: 20 }}>
        🎬 Loading timeline...
      </div>
    );
  }

  if (error || !data) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100vh', fontSize: 16 }}>
        <div style={{ fontSize: 40, marginBottom: 20 }}>📂</div>
        <div style={{ color: '#f44336' }}>No project data loaded</div>
        <div style={{ color: '#888', marginTop: 8, fontSize: 13 }}>
          {error || 'Put project.json + timeline_data.json in the project directory'}
        </div>
      </div>
    );
  }

  const totalWidth = data.total_duration * PX_PER_SEC * zoom;
  const trackRows: React.ReactNode[] = [];
  const trackHeight = 56;
  const totalHeight = Object.keys(data.tracks).length * trackHeight;

  // Ruler marks
  const rulerMarks: React.ReactNode[] = [];
  const step = zoom >= 2 ? 1 : zoom >= 1 ? 2 : 5;
  for (let t = 0; t <= data.total_duration; t += step) {
    const left = t * PX_PER_SEC * zoom;
    rulerMarks.push(
      <div
        key={t}
        style={{
          position: 'absolute',
          left,
          top: 0,
          height: '100%',
          borderLeft: t % 5 === 0 ? '1px solid #666' : '1px solid #333',
        }}
      >
        {t % 5 === 0 && (
          <span style={{ position: 'absolute', top: 2, left: 4, fontSize: 10, color: '#888' }}>
            {formatTime(t)}
          </span>
        )}
      </div>
    );
  }

  // Build track rows
  let trackIndex = 0;
  for (const [name, items] of Object.entries(data.tracks)) {
    if (items.length === 0) continue;
    const color = TRACK_COLORS[name] || '#666';

    const clips = items.map((item: any, i: number) => {
      const left = item.start * PX_PER_SEC * zoom;
      const width = Math.max(item.duration * PX_PER_SEC * zoom, 8);
      return (
        <div
          key={i}
          title={`${item.label} (${item.duration.toFixed(1)}s @ ${item.start.toFixed(1)}s)`}
          style={{
            position: 'absolute',
            left,
            top: 4,
            width,
            height: trackHeight - 8,
            background: item.color || color,
            borderRadius: 4,
            opacity: 0.85,
            display: 'flex',
            alignItems: 'center',
            padding: '0 6px',
            overflow: 'hidden',
            cursor: 'pointer',
          }}
        >
          {width > 30 && (
            <span
              style={{
                fontSize: Math.min(10, width / 6),
                whiteSpace: 'nowrap',
                color: '#fff',
                textShadow: '0 1px 2px #000',
              }}
            >
              {item.label.slice(0, Math.max(3, Math.floor(width / 8)))}
            </span>
          )}
        </div>
      );
    });

    trackRows.push(
      <div
        key={name}
        style={{ display: 'flex', height: trackHeight, margin: '1px 0' }}
      >
        <div
          style={{
            width: 140,
            minWidth: 140,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            paddingRight: 12,
            fontSize: 11,
            color: '#888',
            textTransform: 'uppercase',
            letterSpacing: 1,
          }}
        >
          {name}
        </div>
        <div
          style={{
            position: 'relative',
            flex: 1,
            height: '100%',
            background: '#0f0f23',
            borderRadius: 4,
            overflow: 'hidden',
          }}
        >
          {clips}
        </div>
      </div>
    );
    trackIndex++;
  }

  // Transcript
  const transcriptItems = data.transcript.slice(0, 50).map((seg: any, i: number) => (
    <div
      key={i}
      style={{
        padding: '3px 10px',
        fontSize: 11,
        borderBottom: '1px solid #222',
        cursor: 'pointer',
      }}
      onClick={() => setPlayTime(seg.start)}
    >
      <span style={{ color: '#4CAF50', marginRight: 8, fontWeight: 'bold' }}>
        {formatTime(seg.start)}
      </span>
      {seg.text}
    </div>
  ));

  // Receipt
  const receiptItems = data.receipt
    ? Object.entries(data.receipt)
        .filter(([k]) => k !== 'total')
        .map(([k, v]) => (
          <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
            <span style={{ color: '#888' }}>{k}</span>
            <span>{typeof v === 'number' ? `$${v.toFixed(3)}` : String(v)}</span>
          </div>
        ))
    : null;

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', fontSize: 13 }}>
      {/* Header */}
      <div style={{ background: '#16213e', padding: '10px 20px', borderBottom: '2px solid #4CAF50' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span style={{ color: '#4CAF50', fontSize: 14, fontWeight: 'bold' }}>
              ▶▶▶ VIDEO KITCHEN — Timeline
            </span>
            <span style={{ color: '#888', marginLeft: 10, fontSize: 12 }}>
              {data.project_id}
            </span>
          </div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            {/* Playback controls */}
            <button
              onClick={() => {
                if (playTime >= data.total_duration) {
                  setPlayTime(0);
                  setPlaying(true);
                } else {
                  setPlaying(!playing);
                }
              }}
              style={{
                background: playing ? '#f44336' : '#4CAF50',
                border: 'none',
                borderRadius: 4,
                padding: '4px 12px',
                color: '#fff',
                cursor: 'pointer',
                fontSize: 12,
              }}
            >
              {playing ? '■ STOP' : '▶ PLAY'}
            </button>
            <span style={{ color: '#aaa', fontSize: 11 }}>
              {formatTime(playTime)} / {formatTime(data.total_duration)}
            </span>
            {/* Zoom */}
            <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
              <button
                onClick={() => setZoom((z) => Math.max(0.5, z - 0.5))}
                style={{ background: '#333', border: 'none', borderRadius: 3, padding: '2px 6px', color: '#fff', cursor: 'pointer', fontSize: 11 }}
              >
                −
              </button>
              <span style={{ color: '#888', fontSize: 10 }}>{zoom.toFixed(1)}x</span>
              <button
                onClick={() => setZoom((z) => Math.min(4, z + 0.5))}
                style={{ background: '#333', border: 'none', borderRadius: 3, padding: '2px 6px', color: '#fff', cursor: 'pointer', fontSize: 11 }}
              >
                +
              </button>
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 15, marginTop: 6, fontSize: 11, color: '#aaa' }}>
          <span>🎬 {data.total_duration.toFixed(1)}s</span>
          <span>📝 {data.transcript.length} segments</span>
          <span>🗂️ {data.w24?.idProduction || '-'}</span>
          <span>📅 {data.w24?.sendungVom || '-'}</span>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', background: '#0f3460' }}>
        {[
          { id: 'timeline', label: '🎬 Timeline' },
          { id: 'transcript', label: '📝 Transcript' },
          { id: 'receipt', label: '🧾 Receipt' },
          { id: 'info', label: 'ℹ️ Info' },
        ].map((t) => (
          <div
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              padding: '8px 16px',
              cursor: 'pointer',
              fontSize: 12,
              borderBottom: tab === t.id ? '2px solid #4CAF50' : '2px solid transparent',
              color: tab === t.id ? '#4CAF50' : '#888',
              background: tab === t.id ? '#1a1a2e' : 'transparent',
            }}
          >
            {t.label}
          </div>
        ))}
      </div>

      {/* Tab content */}
      {tab === 'timeline' && (
        <div style={{ flex: 1, overflow: 'auto', position: 'relative' }}>
          {/* Ruler */}
          <div
            style={{
              position: 'sticky',
              top: 0,
              zIndex: 10,
              height: 22,
              marginLeft: 140,
              borderBottom: '1px solid #333',
              background: '#1a1a2e',
              minWidth: totalWidth + 20,
            }}
          >
            {rulerMarks}
          </div>

          {/* Color legend */}
          <div
            style={{
              display: 'flex',
              gap: 12,
              margin: '6px 0 6px 140px',
              fontSize: 10,
            }}
          >
            {Object.entries(TRACK_COLORS).map(([name, color]) => (
              <div key={name} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <div style={{ width: 10, height: 10, borderRadius: 2, background: color }} />
                <span style={{ color: '#666' }}>{name}</span>
              </div>
            ))}
          </div>

          {/* Tracks */}
          <div style={{ position: 'relative' }}>
            {trackRows}

            {/* Playhead cursor */}
            {playTime > 0 && (
              <div
                style={{
                  position: 'absolute',
                  left: 140 + playTime * PX_PER_SEC * zoom,
                  top: 0,
                  bottom: -20,
                  width: 2,
                  background: '#ff4444',
                  pointerEvents: 'none',
                  zIndex: 20,
                  boxShadow: '0 0 4px #ff4444',
                }}
              />
            )}
          </div>
        </div>
      )}

      {tab === 'transcript' && (
        <div style={{ flex: 1, overflow: 'auto', padding: 10 }}>
          <div style={{ color: '#4CAF50', marginBottom: 8, fontSize: 12 }}>
            📝 Transcript ({data.transcript.length} segments)
          </div>
          {transcriptItems}
        </div>
      )}

      {tab === 'receipt' && data.receipt && (
        <div style={{ flex: 1, overflow: 'auto', padding: 20 }}>
          <div
            style={{
              background: '#0f0f23',
              border: '1px solid #333',
              borderRadius: 8,
              padding: 20,
              maxWidth: 400,
              lineHeight: 1.8,
            }}
          >
            <div style={{ color: '#4CAF50', textAlign: 'center', marginBottom: 10, fontSize: 14 }}>
              🧾 VIDEO KITCHEN
            </div>
            {receiptItems}
            <div
              style={{
                borderTop: '1px solid #333',
                paddingTop: 8,
                fontWeight: 'bold',
                color: '#4CAF50',
                display: 'flex',
                justifyContent: 'space-between',
              }}
            >
              <span>TOTAL</span>
              <span>${(data.receipt.total || 0).toFixed(3)}</span>
            </div>
          </div>
        </div>
      )}

      {tab === 'info' && (
        <div style={{ flex: 1, overflow: 'auto', padding: 10 }}>
          <div style={{ color: '#4CAF50', marginBottom: 8, fontSize: 12 }}>ℹ️ Project Info</div>
          <pre
            style={{
              background: '#0f0f23',
              padding: 15,
              borderRadius: 8,
              fontSize: 11,
              lineHeight: 1.6,
              overflow: 'auto',
              maxHeight: 'calc(100vh - 200px)',
            }}
          >
            {JSON.stringify({ ...data.meta, ...data.w24 }, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

export default App;