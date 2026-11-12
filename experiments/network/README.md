# The syndrome network under load

How long the decoder waits for a complete round of syndrome frames from N controllers (the transport
time T_up of the paper), as a function of N, topology, link and frame size. The experiment computes it
twice, with a network-calculus bound and with a discrete-event simulation (SimPy), and both are built
from the same path model. The paper's Fig. 5 (N1) is drawn from its statistics by `analysis/network`.

## Usage

Every setting of the runs is in `config.toml`; the sourced constants are two tables in `data/literature/`:
`network_parameters.csv` (cycle time, reaction budget, controller sizes, bits per outcome, Ethernet framing,
node delays, saturation anchor) and `network_links.csv` (the links of the paper's network table), each value
with its source. The experiment writes its data into `build/data/network/` of the repository (the layout of
`data/zenodo/network/`, where the recorded campaign lies if present); it never writes into `data/`.

```
make                # list the targets
make data           # the whole experiment: load model, bounds, simulation runs, statistics
make load           # frame sizes of the load model -> load/
make bound          # network-calculus bounds, crossings, R x L grid, saturation -> bound/
make simulate       # all simulation runs -> sim/raw/; runs whose file exists are skipped, so a stopped run resumes
make stats          # statistics of the simulation runs (paths.runs) -> sim/stats/
make sanity         # plausibility checks -> SANITY.md
make check          # regenerate the recorded tables into build/check/network and compare
make test           # unit and regression tests
make env            # machine and package versions -> env/ENVIRONMENT.md
make clean          # remove this experiment's folders under build/
make <target> CONFIG=<file>   # another settings file
```

The first target creates a virtual environment in `.venv` from the pinned versions in
`env/requirements.txt` (pytest from `env/requirements-test.txt`). The simulations take about 7 hours with
12 worker processes (`simulate.workers` in `config.toml`; 0 = all cores but two), almost all of it in two
runs: T3 on the jittered link L3 at N = 16,000. The other stages take seconds. The statistics read the runs in
`paths.runs`, by default this experiment's own. Every stage is also available on its own:

```
.venv/bin/python -m qecnet [--config FILE] load | bound | stats | sanity | check
.venv/bin/python -m qecnet [--config FILE] simulate {checks,s1,s3,edge} [--workers W] [--match REGEX]
```

`make check` computes the load model, the bounds and the statistics of the recorded runs
(`data/zenodo/network/sim/raw`) into `build/check/network/` and requires every table to be identical to the
recorded one; without the recorded campaign it is skipped. The simulation is deterministic, so the runs of
`make simulate` equal the recorded runs.

## Layout

| Path | Content |
|---|---|
| `config.toml` | paths and the settings of the runs: sweep, scenarios, simulated cycles, seeds, R x L grid, workers |
| `qecnet/parameters.py` | the parameters as the modules use them, read from `config.toml` and `network_parameters.csv` |
| `qecnet/links.py` | `Link` (rate, latency, framing, where the latency is charged, source row), read from `network_links.csv` |
| `qecnet/frames.py` | load model: outcomes, payload and frame bits per controller and cycle; `load/frame_sizes.csv` |
| `qecnet/topologies.py` | the path model: `Hop` and `Node` stages, and the topologies `Direct` (T1), `Star` (T2, T4) and `Tree` (T3, T3-k7) that turn a link and N into a path |
| `qecnet/configuration.py` | `Config`: one configuration, its id, seed, path and frame sizes |
| `qecnet/calculus.py` | the network-calculus bound, the crossing N and the path formula |
| `qecnet/simulation.py` | the discrete-event simulation, built from the same path |
| `qecnet/jobs.py` | the four sets of simulated configurations and their cycle counts |
| `qecnet/runner.py` | parallel simulation runs -> `sim/raw/` |
| `qecnet/bounds.py` | `bound/` tables |
| `qecnet/stats.py` | `sim/stats/` tables |
| `qecnet/sanity.py` | `SANITY.md`, the plausibility checks |
| `qecnet/check.py` | comparison of the output with the recorded tables |
| `qecnet/data.py` | `DataDir`: the output folder and the runs folder every stage receives |
| `qecnet/__main__.py` | command line |
| `tests/` | unit tests of the settings, load model, links, bound, simulation and comparison; regression tests against the recorded data |
| `env/` | pinned requirements, `collect_env.sh` |

Every configuration is a value object (`Config`); links and topologies are looked up by name
(`links.LINKS`, `topologies.TOPOLOGIES`). A topology is a strategy: it decides how controllers are
grouped behind nodes and builds the path, and both the bound and the simulation use that path, so they
cannot drift apart. The settings are read once (`parameters.py`); the output and runs folders are passed in.

## Data model (tidy)

**`load/frame_sizes.csv`**: one row per (Q_c, b, burst, link): `Q_c, q, b, burst, link, payload_bits,
frame_bits, rate_bps_at_1.1us, source` plus `outcomes, framing, line_rate_bps` (table),
`link_rate_bps` (after line coding) and `serialisation_ns`.

**`bound/bounds.csv`**: one row per configuration: `topology, link, N, scenario, aggregation,
bound_ns, formula` plus `Q_c, Q_total, bound_steady_ns, bound_burst_ns` (S3), `k`, `root_ports`,
`root_ports_exceed_published` (T3), `frame_bits, cycle_ns, utilisation, stable,
switch_latency_assumed, config_id`. Unstable configurations have no `bound_ns`.
**`bound/crossings.csv`**: one row per (configuration family, budget, cycle class): `N_cross`
(largest integer N whose bound stays below the budget; empty = no crossing up to N = 10^7, 0 =
misses at N = 1), `Q_total_cross`, `limit` (latency or throughput), the aggregate rate and port
utilisation at the crossing, `k_at_cross`, `root_ports_at_cross`. **`bound/grid.csv`**: the R x L
grid (`topology, scenario, Q_c, R_gbps, L_ns, budget, N_cross, Q_total_cross, limit,
aggregate_bps_at_cross, utilisation_at_cross, frame_bits, formula`); `grid_points.csv` places the
table's links on it; `saturation.csv` gives the saturation condition N F / R < T_c.

**`sim/raw/<topology>_<link>_<scenario>_agg<0|1>_Qc<Q_c>_N<N>.csv.gz`**: one row per recorded cycle:

```
config_id,topology,link,link_rate_bps,hop_latency_ns,scenario,frame_bits,aggregation,Q_c,q,N,cycle_ns,cycle,round_completion_ns,max_queue_frames,utilisation,seed,burst
```

`config_id = net/<topology>/<link>/<scenario>/agg<0|1>/Qc<Q_c>/N<N>`; the S3 scenario carries its
burst period (`S3-d13`), so the d sweep has distinct ids. `round_completion_ns` is the arrival of
the last frame of the cycle at the decoder minus the instant the controllers sent the round,
`cycle` x `cycle_ns` (the T_up sample; a round is sent as soon as it is measured, after T_meas and T_syn).
`max_queue_frames` and `utilisation` are those of the most loaded port of the cycle's window
(the ports into the decoder: aggregator uplink, switch port, leaf uplinks; T1: a controller
link). `burst` is in every file (0 outside S3). `sim/raw/meta/<stem>.json` holds cycles, seed,
wall time and per-port offered load and maximum queue; `sim/raw/checks/` the anchor and grid
runs (scenario tags `@Tc500-84B`, `@single-hop`); `sim/raw/edge/` N1's families at their largest
stable N and the next N, kept apart so that the sweep's counts do not change.

**`sim/stats/summary_long.csv`**: one row per (configuration, `cycle_class`, `statistic`, `value`);
`cycle_class` = `steady` or `burst` (S3). Timing statistics, as in the decoder experiment: mean,
median, p90, p99, p999, max, min, std (ns); further `range_ns`, `range_by_phase_ns` (S3),
`bound_ns` (of the cycle class), `bound_over_max`, `offered_load`, `stable`, `max_queue_frames`,
`utilisation_mean/max`, `cycles_recorded`, `seed`. Unstable configurations have no timing
statistics, only `queue_growth_ns_per_cycle`. `summary.csv` is the wide pivot;
`checks_summary*.csv` the same for the checks, `edge_summary*.csv` for the edge set; `ports.csv`,
`grid_diagonal.csv`, `anchor1.csv`.

## Model

Links, row by row from the paper's network table:

| link | table row | R used | L used |
|---|---|---|---|
| L1 | B2 Riverlane QECi / QECIPHY: 190-220 ns per link, 12.5 Gb/s per lane | 12.5 Gb/s | 205 ns (mid-range), per link hop |
| L2 | B2 Eos transceiver (Yale, DECONET): 95 ns, 16 Gb/s | 16 Gb/s | 95 ns, per link hop |
| L3 | B2 Lightweight GT link (QubiC/UMD, Liu et al.): 157 ns one-way, +-16 ns forward, 10 Gb/s | 10 x 64/66 Gb/s | uniform on [141, 173] ns per frame and hop |
| L4 | B1 Optical Ethernet, FPGA MAC (Bristol): 361.6 ns, 64 B frame, 10 GbE B2B | 10 Gb/s | 361.6 ns including one 84 B frame |
| L5 | B2 10GbE FPGA syndrome aggregator (Kumamoto, Sakata): ~450 ns, 10 Gb/s per port | 10 and 100 Gb/s | 450 ns per traversal of the aggregator |
| L6 | no table row: commodity switch | 10 and 100 Gb/s | 400 ns per traversal, **assumed** |
| L7 | B2 Aurora 64B/66B (AMD IP): 450 ns one-way, up to 25.8 Gb/s per lane | 25.8 x 64/66 Gb/s | 450 ns, per link hop |

- Frames: payload = q b bits + 8 B header; Ethernet (L4-L6) max(84 B, payload + 38 B) on the wire,
  custom serial links (L1-L3, L7) the payload. q = Q_c / 2 ancillas per cycle; 2q in a burst cycle.
- Latency is charged once on the element it was measured on: link figures on every link hop,
  the aggregator and switch figures once per traversal of the node (their edge links then add
  serialisation only). Sakata et al. measured the aggregator "by connecting another Alveo U55 card
  via QSFP cables" (sec. 3.2), i.e. through both links and the aggregator.
- Topologies: T1 one link per controller into the decoder FPGA; T2 aggregator star, one uplink;
  T3 two-level tree with k = ceil(sqrt N) controllers per leaf and ceil(N/k) leaves, each with
  one uplink into the root; T3-k7 the same tree with k = 7 (the U55's eight 10GbE ports minus the
  uplink, Sakata sec. 2.2 and Table 1); T4 commodity switch. Aggregation on: the aggregator or leaf
  merges the N (k) frames of a cycle into one frame that carries all their outcomes (8 B header + n q b
  bits, at least 84 B on Ethernet) after 450 ns (on L5 this is the measured aggregator itself).
- Path formulas (bound = simulation for fixed latencies): T1 L + F/R (L4: 361.6 ns);
  T2/T4 F/R + L + N F/R; T2 aggregation on F/R + 450 + F_N/R; T3 on custom links
  (L + F/R) + (L + k F/R), aggregation on (L + F/R) + 450 + (L + F_k/R); T3 on L5
  F/R + 450 + k F/R. Stable iff (frames per cycle) x F/R < T_c at every port.
- Release: all controllers at c T_c; S3 bursts in cycles c with c mod d = 0, all controllers at once.
- Cycles: 50 warm-up + 200 recorded (+ 2d in S3) for fixed latencies; 10^4 (10^5 for N <= 1,000)
  on L3. Seeds `BASE_SEED + crc32(config_id) mod 1e6`, recorded per row.

## Modelling decisions

- **Aggregated frame.** The merged frame carries 8 B header + n q b bits (at least 84 B on Ethernet),
  not a frame of the original size: that holds only while all inputs' outcomes fit into one frame (9
  controllers at Q_c = 64 on Ethernet). Sakata's frame format merges per logical qubit (same Step ID
  and Logical Qubit ID), i.e. one merged frame with its own header per logical qubit and round; the
  single merged frame of the model has less overhead, so the aggregation crossings are the optimistic end.
- **Header.** The 8 B application header is an assumption, not taken from Sakata or Liu et al.
  (Sakata's 8 B is the Ethernet preamble; Liu et al. state no header). Sakata's frame format has a
  14 B header (version 2, step ID 8, logical qubit ID 2, payload length 2), which changes no
  Ethernet result here. On the custom links the header is 2/3 of a frame at Q_c = 64; with 2 B the
  Liu tree would cross at 22,801 instead of 5,625 controllers (bound).
- **The 84 B floor.** Sakata's full 46 B payload holds 368 outcomes at b = 1; with the 8 B header the
  limits are 304 outcomes at b = 1, 76 at b = 4 and q = 152 in a burst. So the Ethernet thresholds are
  not crossed in S1 or S3 for any Q_c in {16, 64, 256}; T2 was run at Q_c = 16 and 256 to confirm it,
  and the times are identical to Q_c = 64.
- **Latency accounting.** L5 and L6 are figures of a node (aggregator, switch), not of a link, so
  T2/T4 take L + (N + 1) F/R (the ingress serialisation is added), and with aggregation on the 450 ns
  merge is the measured aggregator, not an extra 450 ns. The 450 ns is added at a custom-link leaf with
  aggregation on (T3 on L2, L3, L7), the only aggregator figure in the table; it includes 10GbE MACs and
  is conservative there (T3/L7 with aggregation then misses 1.1 us at every N).
- **64B/66B.** L3 and L7 serialise at the table's line rate x 64/66, as Liu et al. compute their own
  throughput (sec. V-B2: 4 x 10 x 0.9697 = 38.788 Gb/s) and as the table's 400 Gb/s over 16 Aurora
  lanes implies; no block padding (frame packing not published). L1 and L2 at the table rate (coding
  not stated). `link_rate_bps` in the raw files is the rate used.
- **Tree fan-in.** The balanced tree uses k = ceil(sqrt N). The port-capped tree T3-k7 uses k = 7, not
  8: the U55 has eight 10GbE ports, but one carries the uplink to the BEU ("One of these ports transmits
  data to the BEU", sec. 2.2; "The Rx blocks in Table 1 represent 7 ports"). S3 is not run on T3-k7.
- **Table rows.** L4 is a part-B1 row of the table (controller-to-controller), used for T1. The 100GbE
  rate of L5 is not in the table row (10 Gb/s per port); it comes from Sakata's saturation statement.
  L1's 205 ns is the middle of 190-220 ns.
- **Commercial switches.** Sakata et al. state "commercial switches, which take 300 to 900 ns for
  switching" (sec. 3.2, without source or measurement). L6 stays a declared 400 ns assumption.
- **Saturation anchor.** The saturation holds exactly (8; 75 for "about 80"); the literal p99.9
  crossing of the 500 ns cycle at those N cannot hold with a 450 ns aggregator and is reported as a
  miss with its cause (SANITY.md).
- **Single-hop anchor.** "T3 on L3 with one leaf" is read as one controller on one L3 link into the
  root, Liu et al.'s measured configuration; T3 with a single controller has two L3 hops (334 ns) and is
  reported next to it.
- **Bound per cycle class.** For S3 the bound is computed per phase of the burst period (busy-period
  bound on the staircase), giving separate steady-cycle and burst-cycle bounds.
- **Edge set.** N1 shows the 10GbE variant of each topology and repeats T1 and T4 in the
  aggregation-on panel. The edge set runs each of these families at its largest stable N and the
  next N (16/17 for T2 and T4, 332/333 for T2 with aggregation, 256/257 for T3), so that every line
  runs to where its port saturates; the simulation confirms the bound at all eight.
- **ms case.** One family, T2 on L5 at 10GbE, at the 41.9 ms neutral-atom loop period (Bluvstein et
  al. 2025, one logical teleportation layer; tag `Tc41.9ms`).

## Results at a glance

**Load.** Frames and per-controller rate at T_c = 1.1 us:

| scenario | Q_c | outcomes | payload | Ethernet frame | custom frame | rate per controller (Eth / custom) |
|---|---|---|---|---|---|---|
| S1, b = 1 | 16 / 64 / 256 | 8 / 32 / 128 | 72 / 96 / 192 bit | 84 B | 9 / 12 / 24 B | 611 / 65, 87, 175 Mb/s |
| S2, b = 4 | 16 / 64 / 256 | 8 / 32 / 128 | 96 / 192 / 576 bit | 84 / 84 / 110 B | 12 / 24 / 72 B | 611, 611, 800 / 87, 175, 524 Mb/s |
| S3 burst | 16 / 64 / 256 | 16 / 64 / 256 | 80 / 128 / 320 bit | 84 B | 10 / 16 / 40 B | 611 / 73, 116, 291 Mb/s |

For Q_c <= 256 every Ethernet frame except S2 at Q_c = 256 is 84 B, so the Ethernet results do not
depend on Q_c (T2 at Q_c = 16, 64, 256 give identical times; only the qubit axis changes). On the
custom links serialising 128 outcomes plus header takes 7.7 ns (L7) to 19.8 ns (L3), 15.4 ns on L1,
against a 95-450 ns hop. Syndrome compression is not modelled: on Ethernet the payload of S1 is at
most 24 B of the 46 B the minimum frame carries anyway, so compressing it saves no bit on the wire; on
the custom links the whole frame serialises in at most 20 ns, a fifth of the 100 ns per round CryoZip
budgets for its encoder alone. Cross-check: at N = 300 (19,200 qubits) S2 carries 35 Gb/s of outcomes,
52 Gb/s with custom framing and 183 Gb/s on Ethernet; Mohseni et al.'s ~150 Gb/s counts all 20k
qubits per 550 ns, four times our ancilla-only rate per 1.1 us (140 Gb/s).

**Crossing N (bound; = simulation for fixed latencies) at Q_c = 64, as N (physical qubits).**
"t" = throughput-limited (the port saturates before the latency budget is reached), all others
latency-limited; "never" = no crossing up to N = 10^7 under the model, with the port count it
needs given below.

| topology | link | agg | S1, 1.1 us | S1, 10 us | S2, 1.1 us | S3 steady, 1.1 us | S3 burst, 1.1 us |
|---|---|---|---|---|---|---|---|
| T1 | L1, L2, L4, L7 | 0 | never | never | never | never | never |
| T2 | L5 10GbE | 0 | 8 (512) | 16 (1,024) t | 8 (512) | 8 (512) | 8 (512) |
| T2 | L5 100GbE | 0 | 95 (6,080) | 163 (10,432) t | 95 (6,080) | 95 (6,080) | 95 (6,080) |
| T2 | L5 10GbE | 1 | 170 (10,880) | 332 (21,248) t | 42 | 167 | 85 |
| T2 | L5 100GbE | 1 | 1,998 (127,872) | 3,425 (219,200) t | 499 | 1,808 | 999 |
| T3 | L2 | 0 | 22,500 (1,440,000) | 33,489 (2,143,296) t | 5,476 (350,464) | 20,164 (1,290,496) | 12,544 (802,816) |
| T3 | L3 | 0 | 5,625 (360,000) | 12,321 (788,544) t | 1,369 (87,616) | 5,625 (360,000) | 3,136 (200,704) |
| T3 | L7 | 0 | 2,601 (166,464) | 81,796 (5,234,944) t | 625 (40,000) | 2,601 (166,464) | 1,444 (92,416) |
| T3 | L5 10GbE | 0 | 64 (4,096) | 256 (16,384) t | 64 (4,096) | 64 (4,096) | 64 (4,096) |
| T3 | L2 | 1 | 50,176 (3,211,264) | 299,209 t | 3,025 | 50,176 | 12,321 |
| T3 | L3 | 1 | 7,569 (484,416) | 109,561 t | 441 | 7,569 | 1,849 |
| T3 | L5 10GbE | 1 | 28,900 (1,849,600) | 110,224 t | 1,764 | 27,889 | 7,225 |
| T3 | L7 | 1 | misses at N = 1 (1,358 ns) | 736,164 t | misses | misses | misses |
| T3-k7 | L2, L3, L7, L5 | 0 | never | never | never | never | never |
| T3-k7 | L2, L3, L5 | 1 | never | never | never | never | never |
| T3-k7 | L7 | 1 | misses at N = 1 (1,365 ns) | never | misses | misses | misses |
| T4 | L6 10GbE (assumed) | 0 | 9 (576) | 16 (1,024) t | 9 (576) | 9 (576) | 9 (576) |
| T4 | L6 100GbE (assumed) | 0 | 103 (6,592) | 163 (10,432) t | 103 (6,592) | 103 (6,592) | 103 (6,592) |

Aggregation does not remove N: the merged frame carries all outcomes of its inputs (4 B per
controller at Q_c = 64 instead of an 84 B frame each), so the time still grows with N, about 21
times more slowly on Ethernet; up to 9 controllers the merged frame still fits into 84 B (584 ns).
"Never" is bought with ports: T1 needs N decoder ports; T3 with k = ceil(sqrt N) leaves of k ports and
a root of ceil(N/k) ports (127 and 126 at N = 16,000); T3-k7 buildable leaves but a root of ceil(N/7)
ports, more than the 34 GTs of the largest published root (VCU129, Liu et al.) from N = 239 and 2,286
at N = 16,000. Flat values: T3-k7 (aggregation off) 238 ns on L2, 931 ns on L7, 988 ns on L5,
p99.9 407-418 ns on L3 (bound 425 ns); with aggregation on 664 (L2), 835-836 (L3), 584 (L5) and
1,365 ns (L7). All T4 results: switch latency assumed (400 ns).

- **Burst (S3).** On Ethernet the burst frame stays at 84 B, so the burst cycle costs nothing
  (T2 at 10GbE, d = 5, 13, 25: identical times). It bites on the custom links: the burst cycle
  crosses 1.1 us at N = 3,136 on L3 against 5,625 in the steady state, 1,444 against 2,601 on L7
  and 12,544 against 22,500 on L2, which is the N an aggregator has to be sized for. On L2 the
  steady cycles themselves cross at 20,164 with bursts present: from k = 143 the burst backlog on
  the leaf uplink (143 x 8 ns = 1,144 ns) spills into the next cycle. d changes neither crossing
  (simulated d = 5, 13, 25 identical on T3/L2); it only moves the stability limit.
- **Soft outcomes (S2)** cost nothing on Ethernet up to Q_c = 64 and a factor of about 4 in N on
  the custom links (T3: L3 5,625 -> 1,369, L2 22,500 -> 5,476, L7 2,601 -> 625).
- **R x L grid.** At the 1.1 us budget every cell is latency-limited (utilisation at the crossing
  0.18-0.95); at 10 us every cell is throughput-limited, N = floor(T_c R / F) independent of L
  (utilisation >= 0.98). At 1 Gb/s nothing meets 1.1 us (two serialisations of 84 B take 1,344 ns).
  T2 without aggregation and T4 have identical grids, and at Q_c = 64 S1 and S2 too.
- **Anchors (SANITY.md).** Saturation: N F / R reaches T_c at N = 8 on 10GbE and 75 on 100GbE
  (Sakata: "saturates with eight FEUs", "about 80"); the simulated queue grows from exactly these
  N. The literal "p99.9 crosses the 500 ns cycle at those N" misses: the 450 ns aggregator alone
  is 90 % of that cycle (reported, nothing tuned). T1 on L4: 361.6 ns in every cycle; one L3 hop:
  166.9 ns mean, [150.9, 182.9] ns = Liu et al.'s 157 +- 16 ns plus 9.9 ns serialisation.
- **Tightness.** Bound / simulated maximum = 1.0000 for every configuration with fixed latencies
  (the per-hop sum is attained with one contended port per path); 1.000-1.037 on L3.
- **ms case.** T2 on L5 at the 41.9 ms neutral-atom loop period: stable at every N, 1.08 ms at
  N = 16,000 (serialisation-bound, unchanged by the cycle); crossing of its own cycle at N = 623,504.

## Methods (paper style)

We modelled the transport of one round of syndrome frames from N controllers to the decoder as a
periodic load on a store-and-forward network and evaluated it twice, with a network-calculus
bound and with a discrete-event simulation that are built from the same path description. All
controllers share a clock and release one frame per QEC cycle (T_c = 1.1 us) as soon as the round is
measured. A controller with Q_c physical qubits contributes the outcomes of its q = Q_c/2
ancillas per cycle, and of its data qubits as well in the burst cycle of a lattice-surgery step
(every d-th cycle, all controllers at once); each outcome takes b = 1 bit (hard decisions) or
b = 4 bits (soft information). Every frame carries an 8-byte header; on Ethernet it occupies
max(84 B, payload + 38 B) on the wire, the IEEE 802.3 minimum frame with preamble and
inter-frame gap, and on custom serial links the payload alone. Every output port is a FIFO queue
served at the link rate (after 64B/66B line coding where the source states it), followed by the
per-hop latency of the published technology: per link hop for the FPGA-to-FPGA links (QECIPHY
205 ns, Eos 95 ns, the lightweight GT link of Liu et al. uniformly on 141-173 ns, optical
Ethernet with an FPGA MAC 361.6 ns including one frame, Aurora 450 ns) and once per traversal for
the FPGA syndrome aggregator of Sakata et al. (450 ns, measured through the aggregator) and for a
commodity Ethernet switch (400 ns, an assumption). We evaluated a link per controller into the
decoder FPGA, an aggregator star with a single uplink, a two-level tree with ceil(sqrt N)
controllers per leaf or with seven, the port count of the aggregator board, and a commodity
switch; aggregators either forward frames or combine the frames of a cycle into one frame that
carries all their outcomes by a bitwise OR. The bound adds per-hop horizontal deviations between the
aggregate staircase arrival curve, widened by the delay variation of upstream hops, and a rate-latency
service curve; for aligned frames of equal size it reduces to L + N F/R per contended port. The
simulation (SimPy 4.1.2, one process per controller and per port) records the round-completion
time, the arrival of the last frame of a cycle at the decoder minus the instant the round was sent, for
200 cycles after 50 warm-up cycles, and for 10^4 cycles (10^5 for N <= 1,000) where the link
latency is random; it reproduces the bound exactly for fixed latencies and stays within 3.7 % below
it on the jittered link. A configuration whose offered load reaches one at some port is reported
as unstable with its queue growth per cycle; for all others we report the 99.9th percentile and
the crossing N, the largest number of controllers whose round-completion time stays below the
cycle (or a 10 us reaction budget), together with the number of physical qubits N Q_c.
