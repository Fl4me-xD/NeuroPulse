import asyncio
import json
import math
import random
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import database as db
from Neuromorphic_engine import NeuromorphicSensorNetwork, LIFNeuronState

# ---------------------------------------------------------------------------
# Sensor node definitions
# Each entry: (node_id, beta, threshold)
# Slightly varied parameters mimic real heterogeneous sensor hardware.
# ---------------------------------------------------------------------------

SENSOR_NODES = [
    ("pipeline_stress",   0.80, 1.00),   # Structural stress gauge
    ("water_flow_meter",  0.75, 0.90),   # Municipal flow sensor
    ("vibration_sensor",  0.85, 1.10),   # Bridge / tunnel vibration
    ("pressure_gauge",    0.78, 0.95),   # Water main pressure
]

# ---------------------------------------------------------------------------
# Shared application state (simple in-process store; fine for hackathon)
# ---------------------------------------------------------------------------

class AppState:
    def __init__(self) -> None:
        self.network = NeuromorphicSensorNetwork()
        self.tick: int = 0
        self.anomaly_active: bool = False
        self.anomaly_ticks_remaining: int = 0
        self.anomaly_magnitude: float = 0.0
        self.current_anomaly_event_id: Optional[int] = None
        self.anomaly_spike_count: int = 0
        self.anomaly_peak_potential: float = 0.0
        self.anomaly_start_time: float = 0.0
        # Track connected WebSocket clients
        self.ws_clients: list[WebSocket] = []


state = AppState()


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: initialise DB and sensor network, then run loop."""
    # --- Startup ---
    db.init_db()

    for node_id, beta, threshold in SENSOR_NODES:
        state.network.add_node(node_id, beta=beta, threshold=threshold)
    print(f"[BOOT] Registered {len(SENSOR_NODES)} sensor nodes ✓")

    # Launch the background simulation coroutine
    sim_task = asyncio.create_task(simulation_loop())
    print("[BOOT] Simulation loop started ✓")

    yield  # Application is running

    # --- Shutdown ---
    sim_task.cancel()
    db.close_db()
    print("[SHUTDOWN] NeuroPulse stopped.")


app = FastAPI(
    title="NeuroPulse API",
    description=(
        "Event-Driven Neuromorphic Digital Twin for Smart Autonomous "
        "Infrastructure — NeuroPulse hackathon backend."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Allow the React dev server (localhost:3000) to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten for production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Sensor simulation helpers
# ---------------------------------------------------------------------------

def _normal_sensor_reading(node_id: str, tick: int) -> float:
    """
    Generate a realistic low-amplitude sensor reading for idle conditions.

    Uses a slowly drifting sinusoidal baseline with Gaussian noise.
    The resulting current keeps U(t) well below the LIF threshold so that
    spikes are rare (≈ 5 % of ticks) — mimicking a healthy infrastructure.
    """
    # Slow drift: different frequency per node to break synchrony
    freq_map = {
        "pipeline_stress":  0.03,
        "water_flow_meter": 0.05,
        "vibration_sensor": 0.02,
        "pressure_gauge":   0.04,
    }
    freq = freq_map.get(node_id, 0.03)

    # Baseline ≈ 0.15 ± 0.05 with gentle oscillation
    baseline = 0.15 + 0.05 * math.sin(2 * math.pi * freq * tick)
    noise    = random.gauss(0.0, 0.04)

    # Occasional micro-spike (loose debris, traffic vibration) — rare
    if random.random() < 0.02:
        noise += random.uniform(0.1, 0.25)

    return max(0.0, baseline + noise)


def _anomaly_sensor_reading(node_id: str, magnitude: float) -> float:
    """
    Generate a high-current reading during an injected anomaly event.

    The large current quickly saturates U(t) past U_thr, producing a
    dense cascade of spikes — exactly what judges want to see on the demo.
    """
    # Base shock + per-node random variation + jitter
    shock = magnitude * random.uniform(0.85, 1.15)
    jitter = random.gauss(0.0, 0.08)
    return max(0.0, shock + jitter)


def _compute_frame(tick: int, anomaly_active: bool, magnitude: float) -> dict:
    """
    Step every sensor node and assemble a broadcast-ready frame dict.
    Also persists each step to SQLite and updates anomaly tracking.
    """
    currents: dict[str, float] = {}
    for node_id, *_ in SENSOR_NODES:
        if anomaly_active:
            currents[node_id] = _anomaly_sensor_reading(node_id, magnitude)
        else:
            currents[node_id] = _normal_sensor_reading(node_id, tick)

    # Advance all neurons
    step_results: dict[str, LIFNeuronState] = state.network.step_all(currents)

    # Build per-node payload and persist to DB
    nodes_payload: dict[str, dict] = {}
    tick_spikes = 0
    for node_id, neuron_state in step_results.items():
        neuron = state.network[node_id]
        power_saved = neuron.estimated_power_saved_pct()

        nodes_payload[node_id] = {
            "sensor_value":               round(currents[node_id], 4),
            "membrane_potential":         neuron_state.membrane_potential,
            "spike_fired":                neuron_state.spike_fired,
            "estimated_power_saved_pct":  power_saved,
        }

        if neuron_state.spike_fired:
            tick_spikes += 1

        # Persist to SQLite (non-blocking — lock is very short)
        db.log_sensor_step(
            node_id=node_id,
            sensor_value=currents[node_id],
            membrane_potential=neuron_state.membrane_potential,
            spike_fired=neuron_state.spike_fired,
            estimated_power_saved_pct=power_saved,
            timestamp=time.time(),
        )

    # Network-level summary
    total_steps  = max(state.network[n].total_steps for n, *_ in SENSOR_NODES)
    total_spikes = sum(state.network[n].total_spikes for n, *_ in SENSOR_NODES)
    overall_rate = (total_spikes / (total_steps * len(SENSOR_NODES))) if total_steps else 0.0

    return {
        "timestamp":          time.time(),
        "tick":               tick,
        "anomaly_active":     anomaly_active,
        "nodes":              nodes_payload,
        "network": {
            "any_spike":              tick_spikes > 0,
            "total_spikes_this_tick": tick_spikes,
            "overall_spike_rate":     round(overall_rate, 4),
        },
    }


# ---------------------------------------------------------------------------
# Background simulation loop
# ---------------------------------------------------------------------------

async def simulation_loop() -> None:
    """
    Runs every 100 ms.

    1. Generates sensor readings (normal or anomaly).
    2. Steps the neuromorphic network.
    3. Persists results to SQLite.
    4. Broadcasts the JSON frame to every connected WebSocket client.
    5. Manages anomaly event open / close lifecycle.
    """
    TICK_INTERVAL = 0.1   # seconds — 10 Hz

    print("[SIM] Loop running at 10 Hz …")
    while True:
        state.tick += 1
        tick  = state.tick
        anomaly_on = state.anomaly_active

        # Build and broadcast frame
        frame = _compute_frame(tick, anomaly_on, state.anomaly_magnitude)

        # Anomaly lifecycle bookkeeping
        if anomaly_on:
            spike_this_tick = frame["network"]["total_spikes_this_tick"]
            state.anomaly_spike_count += spike_this_tick

            for node_id, node_data in frame["nodes"].items():
                pot = node_data["membrane_potential"]
                if pot > state.anomaly_peak_potential:
                    state.anomaly_peak_potential = pot

            state.anomaly_ticks_remaining -= 1
            if state.anomaly_ticks_remaining <= 0:
                # Close the anomaly window in the DB
                duration = time.time() - state.anomaly_start_time
                if state.current_anomaly_event_id is not None:
                    db.close_anomaly_event(
                        event_id=state.current_anomaly_event_id,
                        peak_potential=state.anomaly_peak_potential,
                        spike_count=state.anomaly_spike_count,
                        duration_secs=duration,
                    )
                state.anomaly_active = False
                print(
                    f"[SIM] Anomaly resolved after {duration:.2f}s — "
                    f"{state.anomaly_spike_count} spikes fired."
                )

        # Broadcast to all connected clients (safely handle disconnects)
        dead_clients: list[WebSocket] = []
        payload = json.dumps(frame)
        for ws in state.ws_clients:
            try:
                await ws.send_text(payload)
            except Exception:
                dead_clients.append(ws)
        for ws in dead_clients:
            state.ws_clients.remove(ws)

        await asyncio.sleep(TICK_INTERVAL)


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    """
    Persistent WebSocket connection for the React dashboard.

    The simulation loop pushes frames; clients passively receive them.
    Sending any message from the client will be ignored (read-only stream).
    """
    await websocket.accept()
    state.ws_clients.append(websocket)
    print(f"[WS] Client connected — {len(state.ws_clients)} total")
    try:
        while True:
            # Keep the receive buffer drained so the TCP window stays open.
            # Any client message is silently discarded.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in state.ws_clients:
            state.ws_clients.remove(websocket)
        print(f"[WS] Client disconnected — {len(state.ws_clients)} remaining")


# ---------------------------------------------------------------------------
# REST Endpoints
# ---------------------------------------------------------------------------

class AnomalyTriggerRequest(BaseModel):
    magnitude:      float = Field(
        default=3.5,
        ge=1.0,
        le=10.0,
        description=(
            "Current injection magnitude. "
            "1.0 = minor blip; 3.5 = major burst; 10.0 = catastrophic failure."
        ),
    )
    duration_ticks: int = Field(
        default=20,
        ge=5,
        le=200,
        description="How many 100 ms ticks the shock persists (5–200).",
    )


@app.post(
    "/trigger-anomaly",
    summary="Inject a structural anomaly shock into the sensor network",
    tags=["Control"],
)
async def trigger_anomaly(body: AnomalyTriggerRequest):
    """
    Simulates a sudden infrastructure failure event (e.g., a pipe burst,
    bridge stress spike, or pressure surge) by injecting a large input
    current into every LIF neuron.

    The neurons' membrane potentials rapidly exceed U_thr, producing a
    high-frequency cascade of spike trains — the core NeuroPulse demo.
    """
    if state.anomaly_active:
        raise HTTPException(
            status_code=409,
            detail="An anomaly event is already in progress. Wait for it to resolve.",
        )

    # Record the anomaly event in the DB (will be closed in the sim loop)
    event_id = db.open_anomaly_event(
        node_id="all_nodes",
        peak_potential=0.0,
        spike_count=0,
        detected_at=time.time(),
    )

    # Arm the simulation loop
    state.anomaly_active             = True
    state.anomaly_ticks_remaining    = body.duration_ticks
    state.anomaly_magnitude          = body.magnitude
    state.current_anomaly_event_id   = event_id
    state.anomaly_spike_count        = 0
    state.anomaly_peak_potential     = 0.0
    state.anomaly_start_time         = time.time()

    print(
        f"[API] Anomaly triggered — magnitude={body.magnitude}, "
        f"duration={body.duration_ticks} ticks"
    )

    return {
        "status":          "anomaly_injected",
        "magnitude":        body.magnitude,
        "duration_ticks":   body.duration_ticks,
        "duration_seconds": round(body.duration_ticks * 0.1, 1),
        "anomaly_event_id": event_id,
        "message": (
            f"Shock injected. Expect spike burst for ~"
            f"{body.duration_ticks * 0.1:.1f}s on all {len(SENSOR_NODES)} nodes."
        ),
    }


@app.get(
    "/logs",
    summary="Retrieve recent system_log entries",
    tags=["Data"],
)
async def get_logs(node_id: Optional[str] = None, limit: int = 200):
    """Returns up to `limit` recent time-series records, optionally filtered by node."""
    rows = db.fetch_recent_logs(node_id=node_id, limit=limit)
    return {"count": len(rows), "logs": rows}


@app.get(
    "/anomalies",
    summary="List anomaly events",
    tags=["Data"],
)
async def get_anomalies(resolved: Optional[bool] = None, limit: int = 50):
    """Returns anomaly event records. Pass `resolved=true/false` to filter."""
    events = db.fetch_anomaly_events(resolved=resolved, limit=limit)
    return {"count": len(events), "events": events}


@app.get(
    "/power-summary",
    summary="Aggregate power-saving statistics",
    tags=["Data"],
)
async def get_power_summary():
    """Returns overall and per-node estimated power savings vs an ANN baseline."""
    return db.fetch_power_savings_summary()


@app.get(
    "/network-summary",
    summary="Live neuromorphic network state",
    tags=["Data"],
)
async def get_network_summary():
    """Returns real-time neuron statistics for every registered sensor node."""
    return {
        "tick":    state.tick,
        "anomaly_active": state.anomaly_active,
        "nodes":   state.network.network_summary(),
    }


@app.post(
    "/reset",
    summary="Hard-reset all neuron membrane potentials",
    tags=["Control"],
)
async def reset_network():
    """
    Resets every LIF neuron to its resting state (U = 0.0).
    Also clears any active anomaly. Useful between demo runs.
    """
    state.network.reset_all()
    state.anomaly_active          = False
    state.anomaly_ticks_remaining = 0
    return {"status": "reset_complete", "message": "All nodes reset to resting potential."}


@app.get("/", tags=["Meta"])
async def root():
    return {
        "project":     "NeuroPulse",
        "description": "Event-Driven Neuromorphic Digital Twin — NeuroPulse Backend",
        "docs":        "/docs",
        "ws_stream":   "ws://localhost:8000/ws/stream",
        "tick":        state.tick,
        "clients_connected": len(state.ws_clients),
    }
