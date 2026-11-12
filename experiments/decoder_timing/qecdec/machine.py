"""Machine state: snapshots of load, frequency and governor, and a perf_event cycle counter."""
from __future__ import annotations

import ctypes
import datetime as dt
import os
import subprocess
from pathlib import Path


def _read(path: str, default: str = "") -> str:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return default


def snapshot(core: int | None) -> dict:
    la = _read("/proc/loadavg").split()
    try:
        running = int(subprocess.run(["bash", "-c", "ps -eo stat --no-headers | grep -c '^R'"],
                                     capture_output=True, text=True).stdout.strip() or 0)
    except Exception:
        running = -1
    try:
        users = int(subprocess.run(["bash", "-c", "who | wc -l"], capture_output=True, text=True).stdout.strip())
    except Exception:
        users = -1
    c = core if core is not None else 0
    khz = _read(f"/sys/devices/system/cpu/cpu{c}/cpufreq/scaling_cur_freq", "")
    return dict(
        timestamp=dt.datetime.now().isoformat(timespec="seconds"),
        loadavg_1=float(la[0]) if la else None,
        loadavg_5=float(la[1]) if la else None,
        loadavg_15=float(la[2]) if la else None,
        running_procs=running,
        logged_in_users=users,
        core=core,
        cpu_mhz=float(khz) / 1000 if khz else None,
        governor=_read(f"/sys/devices/system/cpu/cpu{c}/cpufreq/scaling_governor", ""),
        boost=_read("/sys/devices/system/cpu/cpufreq/boost", ""),
        perf_event_paranoid=_read("/proc/sys/kernel/perf_event_paranoid", ""),
    )


class CycleCounter:
    """PERF_COUNT_HW_CPU_CYCLES for the calling thread (user space only).

    read() costs about a microsecond (syscall); callers read it outside the
    wall-clock window. Unavailable -> available == False and read() == -1.
    """

    _SYS_perf_event_open = 298  # x86_64
    _PERF_TYPE_HARDWARE = 0
    _PERF_COUNT_HW_CPU_CYCLES = 0

    def __init__(self) -> None:
        self.fd = -1
        self.available = False
        try:
            libc = ctypes.CDLL(None, use_errno=True)
            attr = (ctypes.c_uint64 * 16)()  # 128 bytes, zeroed
            buf = ctypes.cast(attr, ctypes.POINTER(ctypes.c_uint32))
            buf[0] = self._PERF_TYPE_HARDWARE     # type
            buf[1] = 128                          # size
            attr[1] = self._PERF_COUNT_HW_CPU_CYCLES  # config
            attr[5] = (1 << 5) | (1 << 6)         # exclude_kernel | exclude_hv
            fd = libc.syscall(self._SYS_perf_event_open, ctypes.byref(attr),
                              ctypes.c_int(0), ctypes.c_int(-1), ctypes.c_int(-1), ctypes.c_ulong(0))
            if fd >= 0:
                self.fd = fd
                self.available = True
        except Exception:
            self.available = False

    def read(self) -> int:
        if not self.available:
            return -1
        try:
            return int.from_bytes(os.read(self.fd, 8), "little")
        except OSError:
            return -1

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1
