<div align="center">
  <h1>NEUROPULSE [EVENT-DRIVEN SNN DIGITAL TWIN]</h1>
  <h3><i>Ultra-Low Power Smart Infrastructure Monitoring via Neuromorphic Compute</i></h3>
</div>

<div align="center">
  <a href="#">
    <img src="https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=800&q=80" alt="NeuroPulse Project Banner" width="800" style="border-radius: 8px;">
  </a>
</div>

---

## 1. PROJECT OVERVIEW
**NeuroPulse** is an advanced, event-driven digital twin designed for the Open Neuromorphism track at NeuroNex'26. The platform completely reimagines smart city and IoT infrastructure monitoring. By replacing traditional "always-on" Deep Learning architectures with Spiking Neural Networks (SNNs), the system processes real-time sensor data using biological brain-inspired logic. Edge devices remain in a zero-power idle state, transmitting data only when physical deviations trigger an algorithmic "spike," resulting in up to 90% savings in both bandwidth and energy consumption.

## 2. TEAM IDENTITY
<div align="center">

| Name | Role | Institution |
| :---: | :---: | :---: |
| **Nilay Gurdasani** | Team Leader & Full-Stack Architect | VIT Bhopal University |
| **Keshav Maheshwari and Ayush Singh** | SNN engines, Debugging and UI/UX Visualisation | VIT Bhopal University |
| **Tarun Sengar** | Database building and Management | VIT Bhopal University |

</div>

## 3. PROBLEM ANALYSIS
Modern smart city frameworks rely heavily on thousands of IoT edge sensors continuously streaming high-frequency data to centralized cloud servers. This induces three critical structural failures:

* **Prohibitive Power Demands:** Edge devices continuously compute and transmit redundant inputs (the "normal" state), draining localized batteries rapidly.
* **Bandwidth Congestion:** Hundreds of steady data streams clog communication channels, increasing network overhead and server hosting costs.
* **Critical Latency Caps:** Cloud-dependent inference delays emergency localized actions (e.g., shutting off a valve during a pipe burst) due to network round-trip times.

## 4. PROPOSED SOLUTION
NeuroPulse circumvents these limitations by utilizing a temporal, event-driven computing model. Inputs are converted into discrete binary temporal signals (Spike Trains) using the Leaky Integrate-and-Fire (LIF) neuron model: 

$$U(t+1) = \beta \cdot U(t) + I_{in}(t+1) - S(t) \cdot U_{thr}$$

### Core Functionalities:
* **Event-Driven Emulation:** Edge nodes evaluate state streams locally and only emit data packets $S(t) = 1$ when the membrane potential $U(t)$ breaches the threshold.
* **Live Spike-Train Oscilloscope:** A high-fidelity, React-based dashboard that visualizes sub-millisecond network activity and spike cascades in real-time.
* **Comparative Analytics Engine:** Real-time benchmarking comparing Traditional ANN power consumption against the near-zero baseline of the NeuroPulse SNN system.

## 5. TECHNICAL ARCHITECTURE
The system operates on a decoupled, ultra-fast asynchronous architecture.

<div align="center">
  
### Tech Stack Details:
| Layer | Technology | Rationale |
| :--- | :--- | :--- |
| **Frontend** | **React (JS) + Canvas** | Required for rendering high-frequency oscilloscope animations without DOM lag. |
| **Styling** | **Tailwind CSS** | Utilized for custom micro-animations and a dark-mode telemetry aesthetic. |
| **Backend** | **Python (FastAPI)** | Blazing-fast asynchronous execution for managing WebSocket data streams. |
| **SNN Engine** | **snnTorch / Custom LIF** | Pure Python implementation of neuromorphic mathematics and decay thresholds. |
| **Database** | **SQLite** | Lightweight, lock-free local logging for historical hackathon data recording. |

</div>

## 6. SIMULATION & INTERACTION MODES
To effectively demonstrate the technology during the hackathon pitch, the platform features distinct operational states:

* **Normal Operation Mode:** Simulates standard environmental conditions. The system enters an ultra-low power state, emitting only rare calibration spikes. Power savings hover at ~90%.
* **Anomaly Shock Mode:** Injects a sudden, high-magnitude structural deviation (e.g., earthquake vibration or pipeline burst). Judges can visually watch the system cascade into high-frequency spike trains to trigger immediate alerts.

## 7. API & WEBSOCKET SPECIFICATIONS

<div align="center">
  
| Protocol | Endpoint | Description |
| :--- | :--- | :--- |
| `WS` | `/ws/stream` | Opens a persistent bi-directional pipeline pushing frames and spike arrays to the frontend. |
| `POST` | `/trigger-anomaly` | Overrides the background noise generator to force a localized sensory spike across targeted nodes. |
| `GET` | `/metrics/power` | Fetches aggregated energy consumption comparisons between the SNN and baseline ANN. |
| `GET` | `/logs/recent` | Retrieves the last 100 timestamped anomaly and system threshold events from the database. |

</div>

## 8. INSTALLATION AND SETUP
Deploy the digital twin locally using the following steps:

### Backend Configuration:
Navigate to the backend directory, install the required neuro-libraries, and start the asynchronous server:
```bash
cd Backend
pip install fastapi uvicorn websockets snntorch sqlite3
uvicorn main:app --reload
