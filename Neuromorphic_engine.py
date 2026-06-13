"""
NeuroPulse — Neuromorphic Engine
=================================
Implements a Leaky Integrate-and-Fire (LIF) neuron model that converts
continuous sensor readings into discrete binary spike events.

Core formula (discrete temporal dynamics):
    U(t+1) = β · U(t) + I_in(t+1) − S(t) · U_thr

Where:
    U(t)    — membrane potential at time step t
    β       — decay rate (controls how fast potential leaks away)
    I_in    — incoming sensory current (normalised sensor reading)
    S(t)    — binary spike output: 1 if U(t) ≥ U_thr, else 0
    U_thr   — threshold voltage that triggers a spike
"""

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LIFNeuronState:
    """Snapshot of a single neuron's state at a given time step."""
    membrane_potential: float
    spike_fired: bool          # S(t): True when U(t) >= U_thr
    input_current: float       # I_in(t) fed into this step
    timestamp: float = field(default_factory=time.time)


class LIFNeuron:
    """
    Leaky Integrate-and-Fire (LIF) neuron.

    Mimics a biological neuron's sub-threshold membrane dynamics.
    In the NeuroPulse context each instance represents one Smart-City
    monitoring node (e.g., a pipeline stress sensor or a water-flow meter).

    Parameters
    ----------
    beta     : float  — Decay / leak factor (0 < β < 1).  Default 0.8.
    threshold: float  — Voltage threshold U_thr.            Default 1.0.
    reset_val: float  — Potential reset value after spike.  Default 0.0.
    node_id  : str    — Human-readable sensor identifier.
    """

    def __init__(
        self,
        beta: float = 0.8,
        threshold: float = 1.0,
        reset_val: float = 0.0,
        node_id: str = "sensor_node_01",
    ) -> None:
        if not (0.0 < beta < 1.0):
            raise ValueError(f"beta must be in (0, 1), got {beta}")
        if threshold <= 0:
            raise ValueError(f"threshold must be positive, got {threshold}")

        self.beta: float = beta
        self.threshold: float = threshold
        self.reset_val: float = reset_val
        self.node_id: str = node_id

        # Internal membrane potential — U(t)
        self._membrane_potential: float = 0.0

        # Running counters for analytics
        self._total_spikes: int = 0
        self._total_steps: int = 0
        self._spike_log: list[LIFNeuronState] = []

    # ------------------------------------------------------------------
    # Core LIF dynamics
    # ------------------------------------------------------------------

    def step(self, input_current: float) -> LIFNeuronState:
        """
        Advance the neuron by one discrete time step.

        Applies the LIF equation:
            U(t+1) = β · U(t) + I_in(t+1) − S(t) · U_thr

        Parameters
        ----------
        input_current : float
            Normalised sensory event current I_in arriving at this time step.
            Typical range: 0.0 (silence) → >1.0 (anomalous shock).

        Returns
        -------
        LIFNeuronState
            Full state snapshot after the update.
        """
        self._total_steps += 1

        # 1. Check whether previous potential already exceeded threshold
        #    S(t) is evaluated BEFORE the update so the reset term is correct.
        spike = 1 if self._membrane_potential >= self.threshold else 0

        # 2. Apply discrete LIF formula
        new_potential = (
            self.beta * self._membrane_potential   # leak term
            + input_current                         # incoming sensory current
            - spike * self.threshold                # reset term (subtractive)
        )

        # 3. Hard clamp — membrane potential cannot go below reset voltage
        new_potential = max(new_potential, self.reset_val)

        # 4. Commit updated state
        self._membrane_potential = new_potential

        if spike:
            self._total_spikes += 1

        state = LIFNeuronState(
            membrane_potential=round(self._membrane_potential, 6),
            spike_fired=bool(spike),
            input_current=round(input_current, 6),
        )
        self._spike_log.append(state)

        return state

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Hard-reset the neuron to its initial resting state."""
        self._membrane_potential = self.reset_val

    @property
    def membrane_potential(self) -> float:
        """Current membrane potential U(t)."""
        return self._membrane_potential

    @property
    def total_spikes(self) -> int:
        """Cumulative spike count since last reset()."""
        return self._total_spikes

    @property
    def total_steps(self) -> int:
        """Total time steps processed."""
        return self._total_steps

    @property
    def spike_rate(self) -> float:
        """Fraction of steps that produced a spike (0.0 – 1.0)."""
        if self._total_steps == 0:
            return 0.0
        return self._total_spikes / self._total_steps

    def estimated_power_saved_pct(self) -> float:
        """
        Estimate power saved versus an always-on ANN baseline.

        An ANN would transmit every step; the SNN only transmits on spike.
        Power saving ≈ (1 - spike_rate) × 100 %.

        This is a simplified proxy metric suitable for hackathon dashboards.
        """
        return round((1.0 - self.spike_rate) * 100.0, 2)

    def summary(self) -> dict:
        """Return a JSON-serialisable summary of current neuron statistics."""
        return {
            "node_id": self.node_id,
            "membrane_potential": self._membrane_potential,
            "total_steps": self._total_steps,
            "total_spikes": self._total_spikes,
            "spike_rate": round(self.spike_rate, 4),
            "estimated_power_saved_pct": self.estimated_power_saved_pct(),
            "beta": self.beta,
            "threshold": self.threshold,
        }


# ------------------------------------------------------------------
# Multi-node sensor network
# ------------------------------------------------------------------

class NeuromorphicSensorNetwork:
    """
    Manages a collection of LIF neurons representing an array of
    Smart-City sensors (pipeline stress, water flow, vibration, etc.).

    Usage
    -----
        net = NeuromorphicSensorNetwork()
        net.add_node("pipeline_stress",  beta=0.8, threshold=1.0)
        net.add_node("water_flow_meter", beta=0.75, threshold=0.9)

        states = net.step_all({"pipeline_stress": 0.2, "water_flow_meter": 0.15})
    """

    def __init__(self) -> None:
        self._nodes: dict[str, LIFNeuron] = {}

    def add_node(
        self,
        node_id: str,
        beta: float = 0.8,
        threshold: float = 1.0,
        reset_val: float = 0.0,
    ) -> None:
        """Register a new sensor node."""
        if node_id in self._nodes:
            raise ValueError(f"Node '{node_id}' already registered.")
        self._nodes[node_id] = LIFNeuron(
            beta=beta,
            threshold=threshold,
            reset_val=reset_val,
            node_id=node_id,
        )

    def step_all(self, currents: dict[str, float]) -> dict[str, LIFNeuronState]:
        """
        Advance every registered node by one time step.

        Parameters
        ----------
        currents : dict[node_id → input_current]
            Mapping of sensor node IDs to their current input values.
            Missing nodes receive 0.0 (silence).
        """
        results: dict[str, LIFNeuronState] = {}
        for node_id, neuron in self._nodes.items():
            current = currents.get(node_id, 0.0)
            results[node_id] = neuron.step(current)
        return results

    def network_summary(self) -> list[dict]:
        """Return summary dicts for all nodes."""
        return [n.summary() for n in self._nodes.values()]

    def reset_all(self) -> None:
        """Hard-reset every node."""
        for neuron in self._nodes.values():
            neuron.reset()

    def any_spike(self, states: dict[str, LIFNeuronState]) -> bool:
        """Return True if at least one node fired in this time step."""
        return any(s.spike_fired for s in states.values())

    def __getitem__(self, node_id: str) -> LIFNeuron:
        return self._nodes[node_id]