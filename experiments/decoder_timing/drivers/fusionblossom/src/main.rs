//! Per-shot timing driver for fusion-blossom (serial solver), native Rust.
//!
//! Graph input: JSON produced by scripts/build_fb_graph.py (PyMatching's merged
//! matching graph with integer weights). Detection events: Stim b8 file.
//! Per shot the timed window covers solve + subgraph extraction + clear, i.e.
//! everything a decode of one syndrome costs; input conversion is untimed.
//! Timing: std::time::Instant (CLOCK_MONOTONIC), plus perf_event HW cycles.
//!
//! Usage: fb_timing --graph G.json --dets F.b8 --out F.csv [--reps 3] [--warmup 1000] [--floor 10000] [--max_shots N]
//! Output CSV: shot,rep,time_ns,cycles,pred

use fusion_blossom::mwpm_solver::{PrimalDualSolver, SolverSerial};
use fusion_blossom::util::{SolverInitializer, SyndromePattern, VertexIndex};
use serde::Deserialize;
use std::fs::File;
use std::io::{BufWriter, Read, Write};
use std::time::Instant;

#[derive(Deserialize)]
struct Graph {
    vertex_num: u32,
    num_detectors: usize,
    weighted_edges: Vec<(u32, u32, i32)>,
    virtual_vertices: Vec<u32>,
    edge_masks: Vec<u64>,
}

fn open_cycle_counter() -> i32 {
    // struct perf_event_attr laid out by hand (libc does not export it):
    // u32 type @0, u32 size @4, u64 config @8, u64 sample_period @16,
    // u64 sample_type @24, u64 read_format @32, u64 flags @40 (bit5 exclude_kernel, bit6 exclude_hv)
    const SYS_PERF_EVENT_OPEN: libc::c_long = 298; // x86_64
    let mut attr = [0u64; 16];
    attr[0] = (128u64 << 32) | 0u64; // size = 128, type = PERF_TYPE_HARDWARE (0)
    attr[1] = 0; // config = PERF_COUNT_HW_CPU_CYCLES
    attr[5] = (1 << 5) | (1 << 6);
    let fd = unsafe {
        libc::syscall(SYS_PERF_EVENT_OPEN, attr.as_ptr(), 0 as libc::pid_t, -1 as libc::c_int, -1 as libc::c_int, 0 as libc::c_ulong)
    };
    if fd < 0 { -1 } else { fd as i32 }
}

#[inline]
fn read_cycles(fd: i32) -> i64 {
    if fd < 0 { return -1; }
    let mut v: u64 = 0;
    let n = unsafe { libc::read(fd, &mut v as *mut u64 as *mut libc::c_void, 8) };
    if n != 8 { -1 } else { v as i64 }
}

fn arg(name: &str, args: &[String], default: Option<&str>) -> Option<String> {
    for i in 1..args.len().saturating_sub(1) {
        if args[i] == name { return Some(args[i + 1].clone()); }
    }
    default.map(|s| s.to_string())
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let graph_path = arg("--graph", &args, None).expect("--graph");
    let dets_path = arg("--dets", &args, None).expect("--dets");
    let out_path = arg("--out", &args, None).expect("--out");
    let reps: usize = arg("--reps", &args, Some("3")).unwrap().parse().unwrap();
    let warmup: usize = arg("--warmup", &args, Some("1000")).unwrap().parse().unwrap();
    let floor_calls: usize = arg("--floor", &args, Some("10000")).unwrap().parse().unwrap();
    let max_shots: i64 = arg("--max_shots", &args, Some("-1")).unwrap().parse().unwrap();

    // ---- untimed setup ----------------------------------------------------
    let g: Graph = serde_json::from_reader(File::open(&graph_path).expect("graph")).expect("graph json");
    let t_build = Instant::now();
    let initializer = SolverInitializer::new(
        g.vertex_num as fusion_blossom::util::VertexNum,
        g.weighted_edges.iter().map(|&(u, v, w)| (u as VertexIndex, v as VertexIndex, w as fusion_blossom::util::Weight)).collect(),
        g.virtual_vertices.iter().map(|&v| v as VertexIndex).collect(),
    );
    let mut solver = SolverSerial::new(&initializer);
    let graph_build_ns = t_build.elapsed().as_nanos();

    let mut raw = Vec::new();
    File::open(&dets_path).expect("dets").read_to_end(&mut raw).expect("read dets");
    let row_bytes = (g.num_detectors + 7) / 8;
    let mut shots: Vec<Vec<VertexIndex>> = Vec::new();
    for row in raw.chunks_exact(row_bytes) {
        let mut defects = Vec::new();
        for (i, &byte) in row.iter().enumerate() {
            if byte == 0 { continue; }
            for j in 0..8 {
                if byte & (1 << j) != 0 {
                    let idx = i * 8 + j;
                    if idx < g.num_detectors { defects.push(idx as VertexIndex); }
                }
            }
        }
        shots.push(defects);
        if max_shots > 0 && shots.len() as i64 >= max_shots { break; }
    }
    let n = shots.len();
    let masks = &g.edge_masks;
    let cyc_fd = open_cycle_counter();

    let decode = |solver: &mut SolverSerial, defects: &Vec<VertexIndex>| -> u64 {
        let pattern = SyndromePattern::new_vertices(defects.clone());
        solver.solve(&pattern);
        let sub = solver.subgraph();
        let mut pred = 0u64;
        for e in sub { pred ^= masks[e as usize]; }
        solver.clear();
        pred
    };

    // ---- floor: all-zero syndrome ------------------------------------------
    let empty: Vec<VertexIndex> = Vec::new();
    let mut floor_t: Vec<u128> = Vec::with_capacity(floor_calls);
    for _ in 0..floor_calls {
        let t0 = Instant::now();
        let p = decode(&mut solver, &empty);
        let dt = t0.elapsed().as_nanos();
        floor_t.push(dt + (p & 0) as u128);
    }
    floor_t.sort_unstable();
    let floor_med: i128 = if floor_t.is_empty() { -1 } else { floor_t[floor_t.len() / 2] as i128 };

    // ---- warm-up ----------------------------------------------------------
    for i in 0..warmup.min(n) { let _ = decode(&mut solver, &shots[i]); }

    // ---- timed, interleaved repetitions -----------------------------------
    // Note: SyndromePattern construction (a Vec clone of ~100 u32) is inside
    // the window; it is the syndrome hand-over the decoder API requires.
    let mut rec: Vec<(u64, i64, u64)> = vec![(0, 0, 0); reps * n];
    for rep in 0..reps {
        for i in 0..n {
            let c0 = read_cycles(cyc_fd);
            let t0 = Instant::now();
            let pred = decode(&mut solver, &shots[i]);
            let dt = t0.elapsed().as_nanos() as u64;
            let c1 = read_cycles(cyc_fd);
            rec[rep * n + i] = (dt, if c0 < 0 || c1 < 0 { -1 } else { c1 - c0 }, pred);
        }
    }

    // ---- output -----------------------------------------------------------
    let mut out = BufWriter::new(File::create(&out_path).expect("out"));
    writeln!(out, "shot,rep,time_ns,cycles,pred").unwrap();
    for rep in 0..reps {
        for i in 0..n {
            let (t, c, p) = rec[rep * n + i];
            if c >= 0 { writeln!(out, "{},{},{},{},{}", i, rep + 1, t, c, p).unwrap(); }
            else { writeln!(out, "{},{},{},,{}", i, rep + 1, t, p).unwrap(); }
        }
    }
    out.flush().unwrap();
    println!("num_shots={}\nnum_detectors={}\ngraph_build_ns={}\nfloor_ns={}\nfloor_calls={}\ncycles_available={}\nreps={}\nwarmup={}",
             n, g.num_detectors, graph_build_ns, floor_med, floor_calls, if cyc_fd >= 0 { 1 } else { 0 }, reps, warmup);
}
