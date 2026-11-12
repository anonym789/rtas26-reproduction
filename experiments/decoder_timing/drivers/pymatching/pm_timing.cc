// Per-shot timing driver for PyMatching 2 (sparse blossom), native C++.
//
// Mirrors `pymatching predict`: DEM -> matching graph (untimed), then for each
// shot the decode call alone is timed with std::chrono::steady_clock (ns) and,
// if available, hardware cycles via perf_event (PERF_COUNT_HW_CPU_CYCLES).
// All detection-event rows are read into memory before timing starts.
//
// Usage: pm_timing --dem F --dets F.b8 --out F.csv [--reps 3] [--warmup 1000]
//                  [--floor 10000] [--max_shots N]
// Output CSV columns: shot,rep,time_ns,cycles,pred   (cycles = -1 if unavailable)
// Stdout: key=value lines (floor_ns, num_shots, cycles_available, ...).

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#include <linux/perf_event.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <unistd.h>

#include "pymatching/sparse_blossom/driver/mwpm_decoding.h"
#include "pymatching/sparse_blossom/driver/user_graph.h"
#include "stim.h"

static int open_cycle_counter() {
    struct perf_event_attr pe;
    std::memset(&pe, 0, sizeof(pe));
    pe.type = PERF_TYPE_HARDWARE;
    pe.size = sizeof(pe);
    pe.config = PERF_COUNT_HW_CPU_CYCLES;
    pe.disabled = 0;
    pe.exclude_kernel = 1;
    pe.exclude_hv = 1;
    long fd = syscall(SYS_perf_event_open, &pe, 0, -1, -1, 0);
    return fd < 0 ? -1 : (int)fd;
}

static inline long long read_cycles(int fd) {
    long long v = 0;
    if (fd >= 0) {
        if (read(fd, &v, sizeof(v)) != sizeof(v)) return -1;
    } else {
        return -1;
    }
    return v;
}

static inline long long now_ns() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
               std::chrono::steady_clock::now().time_since_epoch())
        .count();
}

static const char *arg(const char *name, int argc, char **argv, const char *def) {
    for (int i = 1; i + 1 < argc; i++)
        if (strcmp(argv[i], name) == 0) return argv[i + 1];
    return def;
}

int main(int argc, char **argv) {
    const char *dem_path = arg("--dem", argc, argv, nullptr);
    const char *dets_path = arg("--dets", argc, argv, nullptr);
    const char *out_path = arg("--out", argc, argv, nullptr);
    int reps = atoi(arg("--reps", argc, argv, "3"));
    size_t warmup = (size_t)atol(arg("--warmup", argc, argv, "1000"));
    size_t floor_calls = (size_t)atol(arg("--floor", argc, argv, "10000"));
    long max_shots = atol(arg("--max_shots", argc, argv, "-1"));
    if (!dem_path || !dets_path || !out_path) {
        std::cerr << "usage: pm_timing --dem F --dets F --out F [--reps R] [--warmup W] [--floor N] [--max_shots N]\n";
        return 2;
    }

    // ---- untimed setup ---------------------------------------------------
    FILE *dem_file = fopen(dem_path, "r");
    if (!dem_file) { std::cerr << "cannot open dem\n"; return 2; }
    stim::DetectorErrorModel dem = stim::DetectorErrorModel::from_file(dem_file);
    fclose(dem_file);
    size_t num_dets = dem.count_detectors();
    size_t num_obs = dem.count_observables();
    if (num_obs > 64) { std::cerr << "too many observables\n"; return 2; }

    auto t_build0 = now_ns();
    pm::Mwpm mwpm = pm::detector_error_model_to_mwpm(dem, pm::NUM_DISTINCT_WEIGHTS, false, false);
    auto t_build1 = now_ns();

    FILE *shots_in = fopen(dets_path, "rb");
    if (!shots_in) { std::cerr << "cannot open dets\n"; return 2; }
    auto fmt = stim::format_name_to_enum_map().at("b8");
    auto reader = stim::MeasureRecordReader<stim::MAX_BITWORD_WIDTH>::make(shots_in, fmt.id, 0, num_dets, 0);
    std::vector<std::vector<uint64_t>> shots;
    stim::SparseShot sparse_shot;
    sparse_shot.clear();
    while (reader->start_and_read_entire_record(sparse_shot)) {
        shots.push_back(sparse_shot.hits);
        sparse_shot.clear();
        if (max_shots > 0 && (long)shots.size() >= max_shots) break;
    }
    fclose(shots_in);
    size_t n = shots.size();

    int cyc_fd = open_cycle_counter();

    // ---- call-overhead floor: all-zero syndrome ---------------------------
    std::vector<uint64_t> empty;
    std::vector<long long> floor_t;
    floor_t.reserve(floor_calls);
    for (size_t i = 0; i < floor_calls; i++) {
        auto t0 = now_ns();
        auto r = pm::decode_detection_events_for_up_to_64_observables(mwpm, empty, false);
        auto t1 = now_ns();
        floor_t.push_back(t1 - t0 + (r.obs_mask & 0));  // keep r alive
    }
    long long floor_med = -1;
    if (!floor_t.empty()) {
        std::sort(floor_t.begin(), floor_t.end());
        floor_med = floor_t[floor_t.size() / 2];
    }

    // ---- warm-up (untimed) -------------------------------------------------
    for (size_t i = 0; i < std::min(warmup, n); i++) {
        auto r = pm::decode_detection_events_for_up_to_64_observables(mwpm, shots[i], false);
        (void)r;
    }

    // ---- timed, interleaved repetitions ----------------------------------
    struct Rec { long long t; long long c; uint64_t pred; };
    std::vector<Rec> rec((size_t)reps * n);
    for (int rep = 0; rep < reps; rep++) {
        for (size_t i = 0; i < n; i++) {
            const auto &hits = shots[i];
            long long c0 = read_cycles(cyc_fd);
            long long t0 = now_ns();
            auto r = pm::decode_detection_events_for_up_to_64_observables(mwpm, hits, false);
            long long t1 = now_ns();
            long long c1 = read_cycles(cyc_fd);
            rec[(size_t)rep * n + i] = Rec{t1 - t0, (c0 < 0 || c1 < 0) ? -1 : c1 - c0, r.obs_mask};
        }
    }

    // ---- output ------------------------------------------------------------
    std::ofstream out(out_path);
    out << "shot,rep,time_ns,cycles,pred\n";
    for (int rep = 0; rep < reps; rep++)
        for (size_t i = 0; i < n; i++) {
            const Rec &r = rec[(size_t)rep * n + i];
            out << i << ',' << rep + 1 << ',' << r.t << ',';
            if (r.c >= 0) out << r.c;
            out << ',' << r.pred << '\n';
        }
    out.close();
    std::cout << "num_shots=" << n << "\nnum_detectors=" << num_dets << "\nnum_observables=" << num_obs
              << "\ngraph_build_ns=" << (t_build1 - t_build0) << "\nfloor_ns=" << floor_med
              << "\nfloor_calls=" << floor_calls << "\ncycles_available=" << (cyc_fd >= 0 ? 1 : 0)
              << "\nreps=" << reps << "\nwarmup=" << warmup << "\n";
    return 0;
}
