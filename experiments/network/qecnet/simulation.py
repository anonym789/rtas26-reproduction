"""Discrete-event simulation of one configuration (SimPy).

One process per controller releases one frame per cycle at c * T_c (all controllers aligned). Every
output port is a FIFO store served by its own process at the link rate, followed by the hop latency.
Nodes forward each frame, or merge the frames of a cycle into one frame that carries all their
children's outcomes, after their processing delay; store-and-forward at every hop. The network is
built from the configuration's path, the same description the bound uses. Single-threaded and
deterministic given the seed, which only drives the latency draws of L3.
"""
from __future__ import annotations

import math
import time
from collections import deque

import numpy as np
import simpy

from .configuration import Config
from .topologies import Hop, Node


class FifoStore(simpy.Store):
    """simpy.Store with a deque: same FIFO order, O(1) get for the long backlogs of unstable ports."""

    def __init__(self, env):
        super().__init__(env)
        self.items = deque()

    def _do_get(self, event):
        if self.items:
            event.succeed(self.items.popleft())


class Frame:
    __slots__ = ("cycle", "bits")

    def __init__(self, cycle: int, bits: int):
        self.cycle = cycle
        self.bits = bits


class Sim:
    """Clock, random latencies and the per-cycle records shared by all elements of the network."""

    def __init__(self, cfg: Config, warmup: int, recorded: int):
        self.cfg, self.T = cfg, cfg.cycle_ns
        self.warmup, self.recorded = warmup, recorded
        self.ncyc = warmup + recorded
        self.env = simpy.Environment()
        self.rng = np.random.Generator(np.random.PCG64(cfg.seed))
        self._u, self._ui = self.rng.uniform(size=1 << 16), 0
        self.rc = np.full(self.ncyc, np.nan)             # round-completion time per cycle
        self.qmax = np.zeros(self.ncyc, dtype=np.int64)  # max occupancy of the tracked ports per cycle
        self.done = self.env.event()

    def uniform(self, lo: float, hi: float) -> float:
        if self._ui == len(self._u):
            self._u, self._ui = self.rng.uniform(size=1 << 16), 0
        u = self._u[self._ui]
        self._ui += 1
        return lo + (hi - lo) * u

    def recorded_cycle(self, c: int) -> bool:
        return self.warmup <= c < self.ncyc

    def later(self, delay: float, fn, arg) -> None:
        ev = self.env.timeout(delay)
        ev.callbacks.append(lambda _ev: fn(arg))


class Port:
    """FIFO output port: serialisation at the link rate, then the hop latency."""

    def __init__(self, sim: Sim, hop: Hop, nxt, role: str, tracked: bool):
        self.sim, self.nxt, self.role, self.tracked = sim, nxt, role, tracked
        self.ns_per_bit = 1e9 / hop.rate
        self.lo, self.hi = hop.lat_lo, hop.lat_hi
        self.store = FifoStore(sim.env)
        self.occ = 0
        self.max_occ_rec = 0
        self.busy_rec = 0.0
        self.busy = np.zeros(sim.ncyc) if tracked else None
        sim.env.process(self.run())

    def put(self, fr: Frame) -> None:
        sim = self.sim
        self.occ += 1
        c = int(sim.env.now // sim.T)
        if self.tracked and c < sim.ncyc:
            if self.occ > sim.qmax[c]:
                sim.qmax[c] = self.occ
        if sim.recorded_cycle(c) and self.occ > self.max_occ_rec:
            self.max_occ_rec = self.occ
        self.store.put(fr)

    def _account(self, t0: float, t1: float) -> None:
        T, busy = self.sim.T, self.busy
        c = int(t0 // T)
        while c < len(busy) and t0 < t1:
            end = min(t1, (c + 1) * T)
            busy[c] += end - t0
            t0, c = end, c + 1

    def run(self):
        sim, env = self.sim, self.sim.env
        while True:
            fr = yield self.store.get()
            ser = fr.bits * self.ns_per_bit
            t0 = env.now
            yield env.timeout(ser)
            self.occ -= 1
            if sim.recorded_cycle(fr.cycle):
                self.busy_rec += ser
            if self.tracked:
                self._account(t0, t0 + ser)
            lat = self.lo if self.lo == self.hi else sim.uniform(self.lo, self.hi)
            if lat > 0:
                sim.later(lat, self.nxt.receive, fr)
            else:
                self.nxt.receive(fr)


class Aggregator:
    """Aggregator, switch or leaf: forwards each frame, or merges the frames of one cycle."""

    def __init__(self, sim: Sim, node: Node, n_children: int):
        self.sim, self.delay, self.aggregate, self.n_children = sim, node.delay, node.aggregate, n_children
        self.count: dict[int, int] = {}
        self.egress: Port | None = None
        # the merged frame carries the outcomes of all children of this node (one header)
        self.merged_bits = sim.cfg.frame_sizes(n_children) if node.aggregate else None

    def receive(self, fr: Frame) -> None:
        if self.aggregate:
            n = self.count.get(fr.cycle, 0) + 1
            if n < self.n_children:
                self.count[fr.cycle] = n
                return
            self.count.pop(fr.cycle, None)  # absent when the node has a single child
            steady, burst = self.merged_bits
            fr = Frame(fr.cycle, burst if self.sim.cfg.is_burst(fr.cycle) else steady)
        if self.delay > 0:
            self.sim.later(self.delay, self.egress.put, fr)
        else:
            self.egress.put(fr)


class Decoder:
    """Records the round-completion time: the arrival of the last frame of a cycle."""

    def __init__(self, sim: Sim, expected: int):
        self.sim, self.expected = sim, expected
        self.cnt = np.zeros(sim.ncyc, dtype=np.int64)
        self.completed = 0

    def receive(self, fr: Frame) -> None:
        sim, c = self.sim, fr.cycle
        self.cnt[c] += 1
        if self.cnt[c] == self.expected:
            sim.rc[c] = sim.env.now - c * sim.T
            if sim.recorded_cycle(c):
                self.completed += 1
                if self.completed == sim.recorded:
                    sim.done.succeed()


def controller(sim: Sim, port: Port, bits: list[int]):
    for c in range(sim.ncyc):
        port.put(Frame(c, bits[c]))
        yield sim.env.timeout(sim.T)


def build(sim: Sim) -> tuple[list[Port], list[Port]]:
    """The network of the configuration's path. Returns (controller ports, node output ports)."""
    cfg = sim.cfg
    stages = cfg.path
    decoder = Decoder(sim, cfg.frames_at_decoder)
    if len(stages) == 1:  # one link per controller into the decoder
        ctrl = [Port(sim, stages[0], decoder, "controller", tracked=(i == 0)) for i in range(cfg.n)]
        return ctrl, []
    hop_in, node, hop_out = stages
    topology = cfg.topology_spec
    group = topology.group(cfg.n)
    nodes, down = [], []
    for g in range(math.ceil(cfg.n / group)):
        nd = Aggregator(sim, node, min(group, cfg.n - g * group))
        nd.egress = Port(sim, hop_out, decoder, f"{topology.node_role} {g}", tracked=True)
        nodes.append(nd)
        down.append(nd.egress)
    ctrl = [Port(sim, hop_in, nodes[i // group], "controller", tracked=False) for i in range(cfg.n)]
    return ctrl, down


def run(cfg: Config, warmup: int, recorded: int) -> dict:
    """Simulate warm-up plus recorded cycles; per-cycle records, per-port load and run metadata."""
    t_wall = time.perf_counter()
    sim = Sim(cfg, warmup, recorded)
    steady, burst = cfg.frame_sizes()
    bits = [burst if cfg.is_burst(c) else steady for c in range(sim.ncyc)]
    ctrl, down = build(sim)
    for p in ctrl:
        sim.env.process(controller(sim, p, bits))
    sim.env.run(until=sim.done)
    tracked = [p for p in ctrl + down if p.tracked]
    util = np.max([p.busy for p in tracked], axis=0) / sim.T
    rec = slice(warmup, sim.ncyc)
    cycles = np.arange(sim.ncyc)[rec]
    per_cycle = dict(cycle=cycles, round_completion_ns=sim.rc[rec], max_queue_frames=sim.qmax[rec],
                     utilisation=util[rec], frame_bits=np.array(bits)[rec],
                     burst=np.array([int(cfg.is_burst(c)) for c in cycles]))
    t_rec = recorded * sim.T
    ports = [dict(port="controller ports", count=len(ctrl),
                  offered_load=max(p.busy_rec for p in ctrl) / t_rec,
                  max_queue_frames=max(p.max_occ_rec for p in ctrl))]
    ports += [dict(port=p.role, count=1, offered_load=p.busy_rec / t_rec, max_queue_frames=p.max_occ_rec)
              for p in down]
    meta = dict(wall_s=time.perf_counter() - t_wall, sim_end_ns=sim.env.now, warmup=warmup, recorded=recorded)
    return dict(per_cycle=per_cycle, ports=ports, meta=meta)
