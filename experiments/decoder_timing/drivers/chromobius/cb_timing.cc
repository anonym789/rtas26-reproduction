// Per-shot timing driver for Chromobius (mobius colour-code decoder), native C++.
//
// DEM -> decoder (untimed), all bit-packed detection-event rows loaded into memory,
// then per shot only chromobius::Decoder::decode_detection_events is timed with
// std::chrono::steady_clock (ns) plus perf_event HW cycles when available.
//
// Usage: cb_timing --dem F --dets F.b8 --out F.csv [--reps 3] [--warmup 1000] [--floor 10000] [--max_shots N]
// Output CSV: shot,rep,time_ns,cycles,pred   (cycles = -1 if unavailable)

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iostream>
#include <span>
#include <string>
#include <vector>

#include <linux/perf_event.h>
#include <sys/syscall.h>
#include <unistd.h>

#include "chromobius/decode/decoder.h"
#include "stim.h"

static int open_cycle_counter() {
    struct perf_event_attr pe;
    std::memset(&pe, 0, sizeof(pe));
    pe.type = PERF_TYPE_HARDWARE;
    pe.size = sizeof(pe);
    pe.config = PERF_COUNT_HW_CPU_CYCLES;
    pe.exclude_kernel = 1;
    pe.exclude_hv = 1;
    long fd = syscall(SYS_perf_event_open, &pe, 0, -1, -1, 0);
    return fd < 0 ? -1 : (int)fd;
}
static inline long long read_cycles(int fd) {
    long long v = 0;
    if (fd < 0 || read(fd, &v, sizeof(v)) != sizeof(v)) return -1;
    return v;
}
static inline long long now_ns() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
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
        std::cerr << "usage: cb_timing --dem F --dets F --out F [--reps R] [--warmup W] [--floor N] [--max_shots N]\n";
        return 2;
    }
    FILE *dem_file = fopen(dem_path, "r");
    if (!dem_file) { std::cerr << "cannot open dem\n"; return 2; }
    stim::DetectorErrorModel dem = stim::DetectorErrorModel::from_file(dem_file);
    fclose(dem_file);
    size_t num_dets = dem.count_detectors();
    size_t num_obs = dem.count_observables();
    size_t row_bytes = (num_dets + 7) / 8;

    auto t_build0 = now_ns();
    chromobius::Decoder decoder = chromobius::Decoder::from_dem(dem, chromobius::DecoderConfigOptions{});
    auto t_build1 = now_ns();

    // all shots into memory (bit-packed rows, exactly the decoder's input format)
    std::ifstream in(dets_path, std::ios::binary);
    if (!in) { std::cerr << "cannot open dets\n"; return 2; }
    std::vector<uint8_t> all((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    size_t n = all.size() / row_bytes;
    if (max_shots > 0 && (size_t)max_shots < n) n = (size_t)max_shots;

    int cyc_fd = open_cycle_counter();

    // call-overhead floor on the all-zero syndrome
    std::vector<uint8_t> zero(row_bytes, 0);
    std::vector<long long> floor_t;
    floor_t.reserve(floor_calls);
    for (size_t i = 0; i < floor_calls; i++) {
        auto t0 = now_ns();
        auto r = decoder.decode_detection_events(std::span<const uint8_t>(zero.data(), row_bytes));
        auto t1 = now_ns();
        floor_t.push_back(t1 - t0 + (long long)(r & 0));
    }
    long long floor_med = -1;
    if (!floor_t.empty()) { std::sort(floor_t.begin(), floor_t.end()); floor_med = floor_t[floor_t.size() / 2]; }

    for (size_t i = 0; i < std::min(warmup, n); i++)
        (void)decoder.decode_detection_events(std::span<const uint8_t>(all.data() + i * row_bytes, row_bytes));

    struct Rec { long long t; long long c; uint64_t pred; };
    std::vector<Rec> rec((size_t)reps * n);
    for (int rep = 0; rep < reps; rep++) {
        for (size_t i = 0; i < n; i++) {
            std::span<const uint8_t> row(all.data() + i * row_bytes, row_bytes);
            long long c0 = read_cycles(cyc_fd);
            long long t0 = now_ns();
            uint64_t pred = decoder.decode_detection_events(row);
            long long t1 = now_ns();
            long long c1 = read_cycles(cyc_fd);
            rec[(size_t)rep * n + i] = Rec{t1 - t0, (c0 < 0 || c1 < 0) ? -1 : c1 - c0, pred};
        }
    }
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
