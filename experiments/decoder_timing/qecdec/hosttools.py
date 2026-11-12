"""Tools for the measurement machine: a queue of single-threaded jobs, each pinned to its own core, and the
choice of the quietest L3 complexes for it."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from .parameters import CONFIG

PACKAGE_PARENT = Path(__file__).resolve().parents[1]


def run_queue(cores: list[int], jobs_file: Path, log_dir: Path, python: str = sys.executable) -> int:
    """Run the jobs of jobs_file (one `decoder code d p [extra measure arguments]` per line) on the given
    cores, one job per core at a time. Jobs whose raw file exists are skipped by the measurement itself.
    Returns the number of failed jobs."""
    jobs = [ln.split() for ln in jobs_file.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    log_dir.mkdir(parents=True, exist_ok=True)
    free = list(cores)
    running: dict[int, tuple[subprocess.Popen, list[str], float]] = {}
    pending = list(jobs)
    print(f"{len(pending)} jobs on cores {cores}", flush=True)
    failures = 0
    while pending or running:
        while pending and free:
            core = free.pop(0)
            job = pending.pop(0)
            dec, code, d, p, *extra = job
            log = log_dir / f"{dec}_{code}_d{d}_p{p}.log"
            cmd = [python, "-m", "qecdec", "--config", str(CONFIG), "measure", "--decoder", dec, "--code", code,
                   "--d", d, "--p", p, "--core", str(core)] + extra
            proc = subprocess.Popen(cmd, stdout=open(log, "a"), stderr=subprocess.STDOUT, cwd=PACKAGE_PARENT)
            running[core] = (proc, job, time.time())
            print(f"[{time.strftime('%H:%M:%S')}] start core {core}: {' '.join(job)}", flush=True)
        for core, (proc, job, t0) in list(running.items()):
            rc = proc.poll()
            if rc is not None:
                del running[core]
                free.append(core)
                status = "ok" if rc == 0 else f"FAILED rc={rc}"
                failures += rc != 0
                print(f"[{time.strftime('%H:%M:%S')}] done  core {core}: {' '.join(job)} {status} ({time.time()-t0:.0f} s)", flush=True)
        time.sleep(2)
    print(f"all jobs finished, {failures} failures", flush=True)
    return failures


def read_stat() -> dict[int, tuple[int, int]]:
    """(idle + iowait, total) jiffies per CPU from /proc/stat."""
    out = {}
    with open("/proc/stat") as f:
        for ln in f:
            if ln.startswith("cpu") and ln[3].isdigit():
                parts = ln.split()
                vals = list(map(int, parts[1:]))
                out[int(parts[0][3:])] = (vals[3] + vals[4], sum(vals))
    return out


def quietest_cores(n: int, socket: int, cores_per_socket: int = 64, l3_size: int = 4, sample: float = 5.0,
                   exclude: set[int] = frozenset()) -> list[int]:
    """The first core of each of the n least busy L3 complexes on a socket, measured over `sample` seconds.
    On the EPYC 7662 cores 4k..4k+3 share an L3; SMT siblings (cpu N + 2 x cores per socket) count too."""
    s0 = read_stat(); time.sleep(sample); s1 = read_stat()
    ncpu = len(s0)
    threads_per_core = ncpu // (2 * cores_per_socket) if ncpu >= 2 * cores_per_socket else 1
    base = socket * cores_per_socket
    scored = []
    for first in range(base, base + cores_per_socket, l3_size):
        cores = list(range(first, first + l3_size))
        if threads_per_core > 1:
            cores += [c + cores_per_socket * 2 for c in cores]
        busy = 0.0
        for c in cores:
            if c in s0 and c in s1:
                idle = s1[c][0] - s0[c][0]; tot = s1[c][1] - s0[c][1]
                busy += 1 - idle / tot if tot else 0
        if first in exclude or any(c in exclude for c in cores):
            continue
        scored.append((busy, first))
    scored.sort()
    return [c for _, c in scored[:n]]
