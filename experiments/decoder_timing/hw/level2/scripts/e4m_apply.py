# Apply the E4 matching print (print-only, after the timed region) to benchmark_decoding.rs in a slot copy.
import sys
from pathlib import Path
p = Path(sys.argv[1]) / "src/cpu/embedded/src/mains/benchmark_decoding.rs"
t = p.read_text()
if "e4m:" in t:
    print("already applied"); sys.exit(0)
old = '''            print!("e4l:");
            for i in 0..core::cmp::min(e4_iters, 64) {
                print!(" {}:{}:{}", e4_iter_layer[i], e4_iter_find[i], e4_iter_resolve[i]);
            }
            println!("");
        }
'''
new = '''            print!("e4l:");
            for i in 0..core::cmp::min(e4_iters, 64) {
                print!(" {}:{}:{}", e4_iter_layer[i], e4_iter_find[i], e4_iter_resolve[i]);
            }
            println!("");
            // E4 matching print (print only, after the timed region): the final matching of the CPU primal module as
            // node pairs "n-m" (node = position in this shot's defect list) or "n-vK" (virtual vertex K); defects that
            // are absent were matched by the accelerator's offloading and never reached the CPU
            print!("e4m:");
            primal_module.iterate_perfect_matching(|_, node, target, _| match target {
                micro_blossom_nostd::util::CompactMatchTarget::Peer(peer) => print!(" {}-{}", node.get(), peer.get()),
                micro_blossom_nostd::util::CompactMatchTarget::VirtualVertex(vertex) => print!(" {}-v{}", node.get(), vertex.get()),
            });
            println!("");
        }
'''
assert t.count(old) == 1, "anchor not found once"
p.with_suffix(".rs.e4m.orig").write_text(t)
p.write_text(t.replace(old, new))
print("applied", p)
