# micro_blossom

Files of the Micro Blossom artifact (Wu et al., arXiv 2502.14787; Zenodo 10.5281/zenodo.14773458), measured on a
Xilinx VMK180 board and copied unchanged. The hardware experiment's calibration reads them
(`experiments/decoder_timing/hw/qechw/microblossom/calibrate.py`).

| Path | From the artifact | Used for |
|---|---|---|
| `board_batch/d_<d>_p_1.0000e-03_N_100000.txt` | board log (tmp-tty) of the batch configuration, d = 9 and 13, p = 1e-3, 100,014 shots | fit of the CPU timeline at d = 9 and its validation at d = 13 |
| `board/d_9_p_1.0000e-03_N_100000.txt` | board log (tmp-tty) of the round-wise-fusion (stream) configuration, d = 9 | the stream-mode CPU timeline that the batch validation compares with |
| `circuit_level_batch/d_<d>.txt` | mean latency per error rate of the batch configuration (`# <p> <average latency> <samples>`) | the artifact's batch means in the validation table |

The board logs hold one latency histogram each, printed by the board's benchmark program.
