FROM golang:1.25.12-bookworm@sha256:6359592445455f2dbe2412bed411336035bc019a50017720d77454ffdd6d0f82 AS go-toolchain
FROM node:22.22.0-bookworm-slim@sha256:dd9d21971ec4395903fa6143c2b9267d048ae01ca6d3ea96f16cb30df6187d94 AS node-toolchain
FROM rust:1.93.0-slim-bookworm@sha256:776861219cd851131c1cec3bbd7cbeb16b99a794048097eb69ad9682a8ed0d57 AS builder
# Debian package snapshot complements the immutable base/toolchain images.
RUN rm -f /etc/apt/sources.list.d/debian.sources && \
    printf '%s\n' 'deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/20260225T000000Z bookworm main' > /etc/apt/sources.list && \
    apt-get update && apt-get install -y --no-install-recommends build-essential clang cmake curl ca-certificates pkg-config python3 time && \
    rm -rf /var/lib/apt/lists/*
COPY --from=go-toolchain /usr/local/go /usr/local/go
COPY --from=node-toolchain /usr/local/bin/node /usr/local/bin/node
COPY --from=node-toolchain /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm
ENV PATH="/usr/local/go/bin:${PATH}" GOTOOLCHAIN=local GOMAXPROCS=4 CARGO_BUILD_JOBS=4 RUSTUP_TOOLCHAIN=1.93.0
WORKDIR /build
COPY examples/robinhood-v4/dependencies.json ./
COPY examples/robinhood-v4/scripts/bootstrap-sources.mjs scripts/
RUN node scripts/bootstrap-sources.mjs
COPY examples/robinhood-v4/tooling/ tooling/
RUN npm ci --prefix tooling --ignore-scripts --no-audit --no-fund
COPY examples/robinhood-v4/scripts/build-precompiles.mjs scripts/
RUN node scripts/build-precompiles.mjs && cd source/nitro && go run -mod=readonly ./solgen
RUN cd source/nitro && cargo build --locked --release --lib -p stylus --features cc_brotli && \
    mkdir -p target/lib target/include && cp target/release/libstylus.a target/lib/libstylus.a
RUN cargo install --locked cbindgen --version 0.29.2 && \
    cd source/nitro/crates/stylus && cbindgen --config cbindgen.toml --crate stylus --output ../../target/include/arbitrator.h
COPY examples/robinhood-v4/native/ native/
RUN cd native && go test -mod=readonly -run TestInvalidation -v && \
    go build -mod=readonly -trimpath -o ../native-runner . && \
    go version -m ../native-runner > ../build-info/go-binary-modules.txt
RUN dpkg-query -W > build-info/debian-packages.txt && \
    du -sk /build /usr/local/cargo /usr/local/go /root/go /root/.cache > build-info/build-disk-kib.txt

FROM node-toolchain AS replay
WORKDIR /repo
COPY core/ core/
COPY runtime/ runtime/
COPY host/ host/
COPY examples/robinhood-v4/ examples/robinhood-v4/
COPY --from=builder /build/native-runner examples/robinhood-v4/native-runner
COPY --from=builder /build/build-info/ examples/robinhood-v4/build-info/
WORKDIR /repo/examples/robinhood-v4
ENTRYPOINT ["node", "scripts/replay.mjs"]
