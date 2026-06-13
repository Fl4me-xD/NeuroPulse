import React, { useState, useEffect, useRef, useCallback } from 'react';
import './App.css';

/* ── Config ── */
const WS_URL = 'ws://localhost:8000/ws/stream';
const SPIKE_BUF = 120;
const TICK_MS  = 100;
const NODE_POSITIONS = [
  {id:'pipeline_stress',  label:'Pipeline',  x:110, y:60},
  {id:'water_flow_meter', label:'Flow',      x:60,  y:130},
  {id:'vibration_sensor', label:'Vibration', x:165, y:130},
  {id:'pressure_gauge',   label:'Pressure',  x:110, y:200},
  {id:'hub_alpha',        label:'HUB-α',     x:38,  y:200},
  {id:'hub_beta',         label:'HUB-β',     x:185, y:60},
];
const EDGES = [
  [0,1],[0,2],[0,3],[1,3],[2,3],[0,5],[1,4],[3,4],[2,5],
];

/* ── Oscilloscope Canvas ── */
function Oscilloscope({ buffer, anomaly }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const W = canvas.offsetWidth, H = canvas.offsetHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, W, H);

    // Grid lines
    ctx.strokeStyle = 'rgba(26,34,54,0.8)';
    ctx.lineWidth = 0.5;
    for (let i = 1; i < 4; i++) {
      const y = (H / 4) * i;
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
    }
    for (let i = 1; i < 8; i++) {
      const x = (W / 8) * i;
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
    }

    // Baseline (center)
    const baseline = H * 0.75;
    const spikeH = H * 0.6;
    const stepW = W / SPIKE_BUF;

    // Draw waveform
    ctx.beginPath();
    buffer.forEach((val, i) => {
      const x = i * stepW;
      const y = val ? baseline - spikeH : baseline + (Math.sin(i * 0.4) * 2);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });

    ctx.strokeStyle = anomaly ? '#c084fc' : '#8b5cf6';
    ctx.lineWidth = anomaly ? 1.5 : 1;
    ctx.shadowColor = anomaly ? '#c084fc' : '#8b5cf6';
    ctx.shadowBlur  = anomaly ? 8 : 4;
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Spike fills
    buffer.forEach((val, i) => {
      if (!val) return;
      const x = i * stepW;
      const grad = ctx.createLinearGradient(x, baseline - spikeH, x, baseline);
      grad.addColorStop(0, anomaly ? 'rgba(192,132,252,0.6)' : 'rgba(139,92,246,0.5)');
      grad.addColorStop(1, 'rgba(139,92,246,0)');
      ctx.fillStyle = grad;
      ctx.fillRect(x - stepW/2, baseline - spikeH, stepW, spikeH);
    });
  }, [buffer, anomaly]);

  return <canvas ref={canvasRef} className="osc-canvas" />;
}

/* ── Brain Grid SVG ── */
function BrainGrid({ nodeStates, anomaly }) {
  const [firing, setFiring] = useState({});
  const [edgePulses, setEdgePulses] = useState([]);

  useEffect(() => {
    const newFiring = {};
    Object.entries(nodeStates).forEach(([id, st]) => {
      if (st && st.spike_fired) newFiring[id] = Date.now();
    });
    if (Object.keys(newFiring).length > 0) {
      setFiring(prev => ({...prev, ...newFiring}));
      const pulseEdges = EDGES
        .filter(() => Math.random() > 0.4)
        .map(e => ({...e, id: Date.now() + Math.random()}));
      setEdgePulses(pulseEdges);
      setTimeout(() => setEdgePulses([]), 800);
    }
  }, [nodeStates]);

  const now = Date.now();
  const scaleX = 0.92, scaleY = 0.88;
  const ox = 8, oy = 8;

  return (
    <svg viewBox="0 0 224 260" className="brain-svg">
      <defs>
        <filter id="glow-p">
          <feGaussianBlur stdDeviation="3" result="blur"/>
          <feComposite in="SourceGraphic" in2="blur" operator="over"/>
        </filter>
        <radialGradient id="node-grad" cx="40%" cy="35%">
          <stop offset="0%" stopColor="#a78bfa"/>
          <stop offset="100%" stopColor="#7c3aed"/>
        </radialGradient>
      </defs>

      {/* Edges */}
      {EDGES.map(([a, b], i) => {
        const n1 = NODE_POSITIONS[a], n2 = NODE_POSITIONS[b];
        const x1 = n1.x * scaleX + ox, y1 = n1.y * scaleY + oy;
        const x2 = n2.x * scaleX + ox, y2 = n2.y * scaleY + oy;
        return (
          <line key={i} x1={x1} y1={y1} x2={x2} y2={y2}
            stroke={anomaly ? 'rgba(139,92,246,0.35)' : 'rgba(26,34,54,1)'}
            strokeWidth="1.5"/>
        );
      })}

      {/* Pulse animations on edges */}
      {edgePulses.map((ep, idx) => {
        const [a, b] = EDGES[idx % EDGES.length];
        const n1 = NODE_POSITIONS[a], n2 = NODE_POSITIONS[b];
        const x1 = n1.x * scaleX + ox, y1 = n1.y * scaleY + oy;
        const x2 = n2.x * scaleX + ox, y2 = n2.y * scaleY + oy;
        const len = Math.hypot(x2-x1, y2-y1);
        return (
          <line key={ep.id} x1={x1} y1={y1} x2={x2} y2={y2}
            stroke={anomaly ? '#f0abfc' : '#8b5cf6'}
            strokeWidth="2.5"
            strokeDasharray={`${len} ${len}`}
            strokeDashoffset={len}
            style={{
              animation: `spike-travel 0.7s ease-out forwards`,
              filter: 'url(#glow-p)'
            }}
          />
        );
      })}

      {/* Nodes */}
      {NODE_POSITIONS.map((n, i) => {
        const x = n.x * scaleX + ox;
        const y = n.y * scaleY + oy;
        const isFiring = firing[n.id] && (now - firing[n.id]) < 400;
        const hasData  = nodeStates[n.id];
        const isActive = hasData && nodeStates[n.id].spike_fired;
        return (
          <g key={n.id}>
            {(isActive || (anomaly && Math.random() > 0.5)) && (
              <circle cx={x} cy={y} r={14} fill="none"
                stroke={anomaly ? '#f0abfc' : '#8b5cf6'}
                strokeWidth="1"
                opacity="0.6"
                style={{animation:'node-fire 0.5s ease-out forwards'}}
              />
            )}
            <circle cx={x} cy={y} r={anomaly ? 8 : 6}
              fill={isActive ? 'url(#node-grad)' : (hasData ? '#1a2236' : '#0f1520')}
              stroke={isActive ? '#8b5cf6' : '#1e2a3e'}
              strokeWidth={isActive ? 2 : 1}
              style={anomaly ? {animation:'node-anomaly 0.4s ease-in-out infinite'} : {}}
              filter={isActive ? 'url(#glow-p)' : undefined}
            />
            <circle cx={x} cy={y} r={3}
              fill={isActive ? '#c4b5fd' : (hasData ? '#475569' : '#1e2a3e')}
            />
            <text x={x} y={y + 17} textAnchor="middle"
              fill={isActive ? '#a78bfa' : '#475569'}
              fontSize="8" fontFamily="Courier New">
              {n.label}
            </text>
          </g>
        );
      })}

      {/* Membrane bars */}
      {NODE_POSITIONS.slice(0,4).map((n, i) => {
        const nd = nodeStates[n.id];
        if (!nd) return null;
        const pot = Math.min(nd.membrane_potential / 1.2, 1);
        const x = n.x * scaleX + ox;
        const y = n.y * scaleY + oy + 22;
        const barW = 30, barH = 3;
        const color = pot > 0.8 ? '#ef4444' : pot > 0.5 ? '#f59e0b' : '#8b5cf6';
        return (
          <g key={'bar'+i}>
            <rect x={x - barW/2} y={y} width={barW} height={barH} rx="1.5" fill="#0f1520"/>
            <rect x={x - barW/2} y={y} width={pot * barW} height={barH} rx="1.5" fill={color}/>
          </g>
        );
      })}
    </svg>
  );
}

/* ── Main App ── */
export default function App() {
  const [mode, setMode] = useState('normal'); 
  const [liveStream, setLiveStream] = useState(false);
  const [anomaly, setAnomaly] = useState(false);
  const [tick, setTick] = useState(0);
  const [spikeBuffer, setSpikeBuffer] = useState(Array(SPIKE_BUF).fill(0));
  const [nodeStates, setNodeStates] = useState({});
  const [totalSpikes, setTotalSpikes] = useState(0);
  const [spikesPerSec, setSpikesPerSec] = useState(0);
  const [snnPower, setSnnPower] = useState(4);
  const [energySaved, setEnergySaved] = useState(91);
  const [flash, setFlash] = useState(false);
  const [eventLog, setEventLog] = useState([]);

  const wsRef = useRef(null);
  const simRef = useRef(null);
  const spikeTimestamps = useRef([]);
  const anomalyTimerRef = useRef(null);

  const addLog = useCallback((node, msg, isSpike=false) => {
    const now = new Date();
    const time = now.toLocaleTimeString('en-GB',{hour12:false});
    setEventLog(prev => [{time, node, msg, isSpike}, ...prev].slice(0, 60));
  }, []);

  /* ── Simulation tick ── */
  const doTick = useCallback((isAnomaly) => {
    setTick(t => t + 1);
    const spikeChance = isAnomaly ? 0.85 : 0.04;
    const nodes = ['pipeline_stress','water_flow_meter','vibration_sensor','pressure_gauge'];
    const newStates = {};
    let tickSpike = false;

    nodes.forEach(id => {
      const spikes = Math.random() < spikeChance;
      const sensorVal = isAnomaly ? 2.8 + Math.random() * 1.5 : 0.12 + Math.random() * 0.08;
      const memPot = isAnomaly ? 0.9 + Math.random() * 0.8 : Math.random() * 0.4;
      newStates[id] = { spike_fired: spikes, sensor_value: sensorVal, membrane_potential: memPot };
      if (spikes) tickSpike = true;
    });

    setNodeStates(newStates);
    setSpikeBuffer(prev => {
      const next = [...prev.slice(1), tickSpike ? 1 : 0];
      return next;
    });

    if (tickSpike) {
      setTotalSpikes(s => s + 1);
      spikeTimestamps.current.push(Date.now());
      if (isAnomaly) addLog('NET', 'CASCADE SPIKE fired', true);
    }

    // Power simulation
    const basePower = isAnomaly ? 55 + Math.random() * 30 : 2 + Math.random() * 5;
    setSnnPower(Math.round(basePower));
    setEnergySaved(Math.round(isAnomaly ? 45 + Math.random() * 20 : 88 + Math.random() * 5));

    // spikes/sec
    const now = Date.now();
    spikeTimestamps.current = spikeTimestamps.current.filter(t => now - t < 1000);
    setSpikesPerSec(spikeTimestamps.current.length);
  }, [addLog]);

  /* ── WebSocket (real backend) ── */
  const connectWS = useCallback(() => {
    try {
      const ws = new WebSocket(WS_URL);
      ws.onopen = () => { addLog('WS', 'Connected to backend'); };
      ws.onmessage = (e) => {
        const data = JSON.parse(e.data);
        setTick(data.tick || 0);
        setAnomaly(data.anomaly_active || false);
        if (data.nodes) setNodeStates(data.nodes);
        
        const spiked = data.network?.total_spikes_this_tick > 0;
        setSpikeBuffer(prev => [...prev.slice(1), spiked ? 1 : 0]);
        if (spiked) { setTotalSpikes(s => s + 1); spikeTimestamps.current.push(Date.now()); }

        const nodes = Object.values(data.nodes || {});
        if (nodes.length) {
          const avg = nodes.reduce((s,n) => s + n.estimated_power_saved_pct, 0) / nodes.length;
          setEnergySaved(Math.round(avg));
          setSnnPower(Math.round(100 - avg));
        }

        const now = Date.now();
        spikeTimestamps.current = spikeTimestamps.current.filter(t => now - t < 1000);
        setSpikesPerSec(spikeTimestamps.current.length);
      };
      ws.onclose = () => { addLog('WS', 'Disconnected'); setLiveStream(false); };
      wsRef.current = ws;
    } catch { addLog('WS', 'Connection failed'); setLiveStream(false); }
  }, [addLog]);

  /* ── Mode handlers ── */
  const handleNormal = () => {
    if (anomalyTimerRef.current) clearTimeout(anomalyTimerRef.current);
    setMode('normal'); setAnomaly(false);
    addLog('SYS', 'Entered normal operation mode');
  };

  const handleAnomaly = async () => {
    setMode('anomaly'); setAnomaly(true);
    setFlash(true); setTimeout(() => setFlash(false), 120);
    addLog('SYS', '⚡ ANOMALY SHOCK injected', true);
    
    if (liveStream) {
      try {
        await fetch('http://localhost:8000/trigger-anomaly', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({magnitude: 3.5, duration_ticks: 30})
        });
      } catch {}
    }

    if (anomalyTimerRef.current) clearTimeout(anomalyTimerRef.current);
    anomalyTimerRef.current = setTimeout(() => {
      setAnomaly(false); setMode('normal');
      addLog('SYS', 'Anomaly resolved — returning to baseline');
    }, 3000);
  };

  const handleStream = () => {
    if (liveStream) {
      wsRef.current?.close(); setLiveStream(false);
      addLog('WS','Stream disconnected');
    } else {
      setLiveStream(true); connectWS();
    }
  };

  /* ── Simulation loop ── */
  useEffect(() => {
    if (liveStream) { clearInterval(simRef.current); return; }
    simRef.current = setInterval(() => doTick(anomaly), TICK_MS);
    return () => clearInterval(simRef.current);
  }, [liveStream, anomaly, doTick]);

  const annPower = 100;

  return (
    <>
      <div className={`flash-overlay ${flash ? 'flashing' : ''}`}/>
      <div className="grid-bg"/>
      
      <div className="shell">
        {/* ── Topbar ── */}
        <header className="topbar">
          <div className="tb-brand">
            <div className="tb-orb"/>
            <div>
              <div className="tb-name">NeuroPulse</div>
              <div className="tb-tag">Neuromorphic Command Center</div>
            </div>
          </div>
          <div className="tb-metrics">
            <div className="tb-metric">
              <div className="tb-metric-label">Tick</div>
              <div className="tb-metric-val" style={{color:'var(--purple)',fontSize:13}}>{tick.toLocaleString()}</div>
            </div>
            <div className="tb-metric">
              <div className="tb-metric-label">Spikes/s</div>
              <div className="tb-metric-val" style={{color: spikesPerSec > 3 ? 'var(--red)' : 'var(--text)',fontSize:13}}>{spikesPerSec}</div>
            </div>
            <div className="tb-metric">
              <div className="tb-metric-label">Energy Saved</div>
              <div className="tb-metric-val" style={{color:'var(--emerald)',fontSize:13}}>{energySaved}%</div>
            </div>
            <div className="tb-status">
              <div className={`tb-dot ${liveStream ? 'live' : anomaly ? 'anomaly' : 'off'}`}/>
              <span style={{fontSize:10,letterSpacing:'0.8px',textTransform:'uppercase',color:'var(--text2)'}}>
                {liveStream ? 'LIVE' : anomaly ? 'ANOMALY' : 'SIM'}
              </span>
            </div>
          </div>
        </header>

        {/* ── Left: Brain Grid ── */}
        <aside className="content-left">
          <div className="sec-label">Smart City Grid</div>
          <div className="brain-grid-wrap">
            <BrainGrid nodeStates={nodeStates} anomaly={anomaly}/>
          </div>
          <div style={{marginTop:8}}>
            {['pipeline_stress','water_flow_meter','vibration_sensor','pressure_gauge'].map(id => {
              const nd = nodeStates[id];
              const label = {pipeline_stress:'Pipeline',water_flow_meter:'Flow Meter',vibration_sensor:'Vibration',pressure_gauge:'Pressure'}[id];
              return (
                <div key={id} style={{display:'flex',justifyContent:'space-between',alignItems:'center',
                  padding:'4px 6px',borderRadius:3,marginBottom:2,
                  background: nd?.spike_fired ? 'rgba(139,92,246,0.08)' : 'transparent'}}>
                  <span style={{fontSize:10,color: nd?.spike_fired ? 'var(--purple)' : 'var(--text3)',letterSpacing:'0.5px'}}>{label}</span>
                  <span style={{fontFamily:'var(--mono)',fontSize:10,color: nd?.spike_fired ? 'var(--purple)' : 'var(--text3)'}}>
                    {nd ? nd.membrane_potential.toFixed(3) : '—'}
                    {nd?.spike_fired && <span style={{color:'var(--purple)',marginLeft:4}}>▲</span>}
                  </span>
                </div>
              );
            })}
          </div>
        </aside>

        {/* ── Center: Oscilloscope + KPIs ── */}
        <main className="content-center">
          <div className="sec-label">
            Spike-Train Oscilloscope
            <span style={{marginLeft:'auto',fontFamily:'var(--mono)',fontSize:9,color: anomaly ? 'var(--red)' : 'var(--purple)',letterSpacing:'1px'}}>
              {anomaly ? '⚡ HIGH-FREQ BURST' : '● MONITORING'}
            </span>
          </div>
          
          <div className="osc-wrap">
            <div className="osc-overlay">
              <div className="osc-label">CH1 — SNN Spike Output S(t)</div>
              <div className="osc-label" style={{color:'var(--text3)'}}>100ms/div · 1.0V/div</div>
            </div>
            <Oscilloscope buffer={spikeBuffer} anomaly={anomaly}/>
          </div>

          <div className="kpi-row">
            <div className="kpi">
              <div className="kpi-label">Total Spikes</div>
              <div className="kpi-val purple">{totalSpikes.toLocaleString()}</div>
              <div className="kpi-sub">events fired</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Spike Rate</div>
              <div className="kpi-val" style={{color: spikesPerSec > 5 ? 'var(--red)' : 'var(--purple)'}}>
                {spikesPerSec}<span style={{fontSize:11,color:'var(--text3)'}}>/s</span>
              </div>
              <div className="kpi-sub">{anomaly ? 'CASCADE ACTIVE' : 'nominal'}</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Power Saved</div>
              <div className="kpi-val emerald">{energySaved}%</div>
              <div className="kpi-sub">vs ANN baseline</div>
            </div>
          </div>

          <div style={{background:'var(--bg2)',border:'1px solid var(--border)',borderRadius:4,padding:'10px 14px'}}>
            <div className="sec-label" style={{marginBottom:8}}>LIF Core — U(t+1) = β·U(t) + I<sub>in</sub> − S(t)·U<sub>thr</sub></div>
            {(() => {
              const nd = nodeStates['pipeline_stress'];
              return (
                <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:8}}>
                  {[
                    {label:'β (decay)',val:'0.800',color:'var(--text2)'},
                    {label:'U(t)',val: nd ? nd.membrane_potential.toFixed(4) : '—', color: nd?.spike_fired ? 'var(--red)' : 'var(--purple)'},
                    {label:'I_in',val: nd ? nd.sensor_value.toFixed(4) : '—', color:'var(--amber)'},
                    {label:'S(t)',val: nd?.spike_fired ? '1  ▲' : '0  —', color: nd?.spike_fired ? 'var(--purple)' : 'var(--text3)'},
                  ].map(item => (
                    <div key={item.label} style={{textAlign:'center'}}>
                      <div style={{fontSize:9,color:'var(--text3)',letterSpacing:'1px',textTransform:'uppercase',marginBottom:4}}>{item.label}</div>
                      <div style={{fontFamily:'var(--mono)',fontSize:13,color:item.color}}>{item.val}</div>
                    </div>
                  ))}
                </div>
              );
            })()}
          </div>
        </main>

        {/* ── Right: Comparison + Log ── */}
        <aside className="content-right">
          <div className="sec-label">Energy Comparison</div>
          
          <div className="energy-saved">
            <div style={{fontSize:9,color:'var(--text3)',letterSpacing:'2px',textTransform:'uppercase',marginBottom:8}}>Total Energy Saved</div>
            <div className="energy-saved-number">{energySaved}<span style={{fontSize:20}}>%</span></div>
            <div className="energy-saved-label">Neuromorphic vs Traditional ANN</div>
            <div style={{marginTop:10,height:'1px',background:'linear-gradient(90deg,transparent,var(--purple),transparent)'}}/>
          </div>

          <div className="compare-section">
            <div className="compare-col">
              <div className="compare-col-label ann">ANN Always-On</div>
              <div className="compare-bar-track">
                <div className="compare-bar-fill" style={{
                  height:`${annPower}%`,
                  background:'linear-gradient(to top,#ef4444,#f97316)',
                  boxShadow:'0 0 12px rgba(239,68,68,0.3)'
                }}/>
              </div>
              <div className="compare-bar-val" style={{color:'var(--red)'}}>100% load</div>
              <div style={{fontSize:9,color:'var(--text3)',marginTop:3}}>Constant drain</div>
            </div>
            <div className="compare-col">
              <div className="compare-col-label snn">SNN Edge</div>
              <div className="compare-bar-track">
                <div className="compare-bar-fill" style={{
                  height:`${snnPower}%`,
                  background:`linear-gradient(to top,${anomaly ? '#ef4444' : '#10b981'},${anomaly ? '#f97316' : '#34d399'})`,
                  boxShadow:`0 0 12px ${anomaly ? 'rgba(239,68,68,0.3)' : 'rgba(16,185,129,0.25)'}`,
                  transition:'height 0.2s ease, background 0.3s ease'
                }}/>
              </div>
              <div className="compare-bar-val" style={{color: anomaly ? 'var(--red)' : 'var(--emerald)'}}>{snnPower}% load</div>
              <div style={{fontSize:9,color:'var(--text3)',marginTop:3}}>{anomaly ? 'Spike burst' : 'Event-driven idle'}</div>
            </div>
          </div>

          <div className="sec-label">Event Log</div>
          <div className="spike-log">
            {eventLog.length === 0 && <div style={{color:'var(--text3)',fontSize:10,padding:4}}>No events yet…</div>}
            {eventLog.map((e,i) => (
              <div key={i} className={`log-row ${e.isSpike ? 'spike-row' : ''}`}>
                <span className="log-time">{e.time}</span>
                <span className="log-node">{e.node}</span>
                <span className={`log-msg ${e.isSpike ? 'spike' : ''}`}>{e.msg}</span>
              </div>
            ))}
          </div>
        </aside>

        {/* ── Control Bar ── */}
        <footer className="controlbar">
          <button className="ctrl-btn ctrl-btn-normal" onClick={handleNormal}>
            <span className="ctrl-btn-dot" style={{background:'var(--emerald)'}}/>
            Simulate Normal Operation
          </button>
          
          <button className={`ctrl-btn ctrl-btn-anomaly ${anomaly ? 'active-btn' : ''}`} onClick={handleAnomaly}>
            <span className="ctrl-btn-dot" style={{background:'var(--red)',animation: anomaly ? 'blink 0.3s infinite' : 'none'}}/>
            {anomaly ? '⚡ ANOMALY ACTIVE' : 'TRIGGER ANOMALY SHOCK'}
          </button>
          
          <button className={`ctrl-btn ctrl-btn-stream ${liveStream ? 'active-btn' : ''}`} onClick={handleStream}>
            <span className="ctrl-btn-dot" style={{background: liveStream ? 'var(--purple)' : 'var(--text3)',animation: liveStream ? 'blink 1.5s infinite' : 'none'}}/>
            {liveStream ? 'Disconnect Stream' : 'Connect Live Stream'}
          </button>
        </footer>
      </div>
    </>
  );
}