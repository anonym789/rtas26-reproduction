# The environment of the reproduction package: R 4.6.1 with the packages of analysis/renv.lock, TeX Live for
# tikzDevice and the figure previews, the three Python versions of the experiments with their pinned packages, and
# the compilers of the CPU experiment's timing drivers. The repository is copied in (without data/zenodo, build/
# and the virtual environments); the outputs go to a mounted build/ (see `make docker` in the Makefile).
FROM rocker/r-ver:4.6.1

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake curl ca-certificates git make pkg-config xz-utils \
        texlive-latex-base texlive-latex-recommended texlive-latex-extra texlive-pictures texlive-fonts-recommended \
        libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev libffi-dev liblzma-dev libncursesw5-dev \
        libgdbm-dev uuid-dev tk-dev libicu-dev libpng-dev \
    && rm -rf /var/lib/apt/lists/*

# Python as recorded by the experiments: 3.14.7 (network), 3.12.8 (CPU decoders), 3.13.1 (hardware), built from the
# python.org sources and installed side by side as python3.14, python3.12 and python3.13; with the shared library,
# which relay-bp's Rust bindings (pyo3) link against
RUN for v in 3.14.7 3.12.8 3.13.1; do \
        curl -fsSL https://www.python.org/ftp/python/$v/Python-$v.tgz | tar -xz -C /tmp \
        && cd /tmp/Python-$v && ./configure --prefix=/usr/local --enable-shared --with-ensurepip=install \
             LDFLAGS="-Wl,-rpath,/usr/local/lib" > /dev/null \
        && make -j"$(nproc)" > /dev/null && make altinstall > /dev/null \
        && cd / && rm -rf /tmp/Python-$v || exit 1; \
    done \
    && ln -s /usr/local/bin/python3.14 /usr/local/bin/python3

# Rust: relay-bp 0.2.2 (hardware experiment) has no binary wheel and is built from source with the Rust version of
# the tested environment; the fusion-blossom timing driver selects its own toolchain (rust-toolchain.toml)
ENV RUSTUP_HOME=/opt/rustup CARGO_HOME=/opt/cargo PATH=/opt/cargo/bin:$PATH
RUN curl -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain 1.97.1 \
    && chmod -R a+rwX /opt/rustup /opt/cargo

# R packages at the versions of analysis/renv.lock
COPY analysis/renv.lock /tmp/renv.lock
RUN Rscript -e 'install.packages("renv", repos = "https://cloud.r-project.org")' \
    && Rscript -e 'renv::restore(lockfile = "/tmp/renv.lock", library = .libPaths()[1], prompt = FALSE)'

# the repository and the experiments' virtual environments
COPY . /repro
WORKDIR /repro
RUN make -C experiments/network .venv/.installed \
    && make -C experiments/decoder_timing .venv/.installed \
    && make -C experiments/decoder_timing/hw .venv/.installed \
    && chmod -R a+rwX /repro

CMD ["make", "help"]
