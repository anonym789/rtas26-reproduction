"""The experiment's settings, read from config.toml."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[1] / "config.toml"


@dataclass(frozen=True)
class RelayVariant:
    name: str
    stop_nconv: int
    description: str
    integer: bool = False              # relay-bp's integer decoder (message magnitudes bounded, priors scaled)
    max_data_value: float | None = None
    data_scale_value: float | None = None

    @property
    def decoder_class(self) -> str:
        return "RelayDecoderI32" if self.integer else "RelayDecoderF32"

    def extra_kwargs(self) -> dict:
        kw = dict(stop_nconv=self.stop_nconv)
        if self.integer:
            kw.update(max_data_value=self.max_data_value, data_scale_value=self.data_scale_value)
        return kw


@dataclass(frozen=True)
class Relay:
    """Relay-BP as configured on IBM's FPGA, and the FPGA's time per iteration."""
    gamma0: float
    gamma_interval: tuple[float, float]
    pre_iter: int
    set_max_iter: int
    num_sets: int
    ns_per_iteration: float
    c0_ns: float
    source: str
    variants: dict[str, RelayVariant]

    def decoder_kwargs(self) -> dict:
        """Keyword arguments of relay-bp's decoders that every variant shares."""
        return dict(gamma0=self.gamma0, pre_iter=self.pre_iter, set_max_iter=self.set_max_iter,
                    num_sets=self.num_sets, gamma_dist_interval=self.gamma_interval)

    @property
    def max_iterations(self) -> int:
        return self.pre_iter + self.num_sets * self.set_max_iter

    @property
    def hard_bound_ns(self) -> float:
        return self.c0_ns + self.ns_per_iteration * self.max_iterations


@dataclass(frozen=True)
class Run:
    variant: str
    d: int
    p: float
    code: str = "bb"
    shots: int = 0          # 0 = every sampled shot

    @property
    def name(self) -> str:
        return f"{self.code}_d{self.d}_p{self.p:g}"


@dataclass(frozen=True)
class Transfer:
    workers: int
    chunk: int
    log_legs: int
    runs: list[Run]


@dataclass(frozen=True)
class Gpu:
    host: str
    remote_root: str
    device: int
    sm_clock_mhz: int
    reps: int
    warmup: int
    cupti_shots: int
    batch_shots: int
    batch_sizes: list[int]
    source: str
    runs: list[Run]
    variants: dict[str, dict]


@dataclass(frozen=True)
class CollectSet:
    source: str
    d: int
    mode: str               # "stream" or "batch"
    chunk: int = 2000       # shots per chunk file (global shot index = chunk number x chunk + k - 1)
    p: float = 1e-3
    logs: str | None = None
    tag: str | None = None

    @property
    def log_folder(self) -> str:
        return self.logs or ("logs_batch" if self.mode == "batch" else "logs")

    @property
    def suffix(self) -> str:
        return self.tag if self.tag is not None else ("batch" if self.mode == "batch" else "")


@dataclass(frozen=True)
class MicroBlossom:
    freq_hz: dict[int, float]
    board_histogram: dict[int, str]
    layers_board: dict[int, int]
    layers_ours: dict[int, int]
    read_latency_a_ns: float
    read_latency_b_ns_mhz: float
    batch_timeline: str
    convert: list[dict]
    container: str
    chunks: dict[int, dict]
    sources: dict[str, dict]
    queues: list[dict]
    collect: list[CollectSet]

    def read_latency_ns(self, f_mhz: float) -> float:
        return self.read_latency_a_ns + self.read_latency_b_ns_mhz / f_mhz

    def job_lines(self, d: int, sources: list[str]) -> list[str]:
        """Simulation jobs of one block: for every chunk of distance d, one line per source,
        `<graph> <defects> <layers> <clock> <log name>` as run_queue.sh reads them."""
        ch, clock = self.chunks[d], f"{self.freq_hz[d] / 1e6:g}e6"
        lines = []
        for k in range(ch["count"]):
            for name in sources:
                src = self.sources[name]
                layers = (self.layers_board if src["layers"] == "board" else self.layers_ours)[d]
                lines.append(f"{src['graph'].format(d=d)} {src['defects'].format(d=d, tag=ch['tag'], k=k)} {layers} {clock} "
                             f"{name}_d{d}_c{k:03d}")
        return lines


@dataclass(frozen=True)
class Syndromes:
    code: str
    d: list[int]
    p: list[float]
    shared_p: list[float]   # error rates whose syndromes are the CPU experiment's (its seeds)
    shots: int


@dataclass(frozen=True)
class Config:
    path: Path
    literature: Path
    data: Path
    campaign: Path
    output: Path
    check: Path
    e2_syndromes: Path
    syndromes: Syndromes
    relay: Relay
    transfer: Transfer
    gpu: Gpu
    microblossom: MicroBlossom = field(repr=False)


def _int_keys(table: dict) -> dict:
    return {int(k): v for k, v in table.items()}


def load(path: Path = DEFAULT) -> Config:
    path = Path(path).resolve()
    with open(path, "rb") as f:
        c = tomllib.load(f)
    base = path.parent
    r = c["relay"]
    relay = Relay(gamma0=r["gamma0"], gamma_interval=tuple(r["gamma_interval"]), pre_iter=r["pre_iter"],
                  set_max_iter=r["set_max_iter"], num_sets=r["num_sets"], ns_per_iteration=r["ns_per_iteration"],
                  c0_ns=r["c0_ns"], source=r["source"],
                  variants={k: RelayVariant(name=k, **v) for k, v in r["variants"].items()})
    t = c["transfer"]
    transfer = Transfer(workers=t["workers"], chunk=t["chunk"], log_legs=t["log_legs"], runs=[Run(**x) for x in t["runs"]])
    g = dict(c["gpu"])
    gpu = Gpu(runs=[Run(**x) for x in g.pop("runs")], variants=g.pop("variants"), **g)
    m = dict(c["microblossom"])
    mb = MicroBlossom(freq_hz=_int_keys(m.pop("freq_hz")), board_histogram=_int_keys(m.pop("board_histogram")),
                      layers_board=_int_keys(m.pop("layers_board")), layers_ours=_int_keys(m.pop("layers_ours")),
                      chunks=_int_keys(m.pop("chunks")), collect=[CollectSet(**x) for x in m.pop("collect")], **m)
    paths = {k: (base / v).resolve() for k, v in c["paths"].items()}
    return Config(path=path, literature=paths["literature"], data=paths["data"], campaign=paths["campaign"],
                  output=paths["output"], check=paths["check"], e2_syndromes=paths["e2_syndromes"],
                  syndromes=Syndromes(**c["syndromes"]), relay=relay, transfer=transfer, gpu=gpu, microblossom=mb)
