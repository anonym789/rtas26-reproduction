# literature

Inputs that no experiment produces: values compiled by hand from publications and standards, one value per row
with its source, and third-party measurement files. Git tracks this folder.

| File | Read by | Contents |
|---|---|---|
| `network_parameters.csv` | network experiment | cycle time, reaction budget, controller sizes, bits per outcome, Ethernet framing, node delays, saturation anchor |
| `network_links.csv` | network experiment | rate, latency, framing and source of every link of the paper's network table |
| `decoder_anchors.csv` | CPU decoder experiment | the published decoding speed the campaign checks first (Sparse Blossom) |
| `hardware_decoders.csv` | none (reference) | published latencies of hardware decoders, each number with the section or page it was read from |
| `hardware_decoders_unverified.csv` | none (reference) | candidates whose numbers could not be verified in the sources |
| `micro_blossom/` | hardware experiment | files of the Micro Blossom artifact (see its README) |
| `trip_technology.csv` | trip time, F3 | per qubit technology: readout, syndrome, correction, cycle and coherence times, reaction budget |
| `trip_interconnect.csv` | trip time | up- and down-link terms per interconnect and platform |
| `trip_decoder_literature.csv` | trip time | published mean (and maximum, where stated) of the literature decoders in F3 |
