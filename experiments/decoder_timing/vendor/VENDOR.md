# Vendored third-party sources

- `chromobius_v1.1.1/{gen,clorco}`: circuit generators from https://github.com/quantumlib/chromobius
  at tag v1.1.1 (commit efae0325e4a8fc13be981434d38e499aa06b989f), Apache-2.0. Used for the superdense
  6.6.6 colour-code memory circuits (`clorco.make_circuit(style="superdense_color_code_Z")`)
  and for the noise model applied to every code (`gen.NoiseModel.uniform_depolarizing(p)`).
  Tests and caches stripped; otherwise unmodified.
- `tesseract_circuits/bb_*.noiseless.stim`: bivariate-bicycle memory circuits from
  https://github.com/quantumlib/tesseract-decoder (testdata/bivariatebicyclecodes, commit
  e7c762eef24161e304ba6fccb856a05b41f88c39), Z-basis memory, rounds = d, with the si1000 noise
  removed (`stim.Circuit.without_noise()`); our noise model is re-applied at syndrome generation.
  Source files: the `p=0.001, c=bivariate_bicycle_Z` variants of nkd=[[144,12,12]] and [[72,12,6]].
