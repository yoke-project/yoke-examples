# yoke-examples — repository justfile
#
# Reference plugins and showcase tools (role: showcase). Conventional targets
# per yoke-meta/docs/justfile-conventions.md.
#
# Each example is one binary in its own directory under plugins/ or tools/, in
# either toolchain:
#   - Go:   <dir>/main.go      (SDK resolved via replace in go.mod)
#   - Rust: <dir>/Cargo.toml   (SDK resolved via a path dependency)
# The list/build recipes discover both automatically, so adding a new example
# needs no justfile change.

set shell := ["bash", "-euo", "pipefail", "-c"]

# ---- Default ---------------------------------------------------------------

# List available recipes
default:
    @just --list

# ---- Discovery -------------------------------------------------------------

# List the discovered examples (plugins/* and tools/*) with their toolchain
list:
    @for d in plugins/*/ tools/*/; do \
        name=$(basename "$d"); \
        if [ -f "$d/main.go" ]; then echo "$name  ($d) [go]"; \
        elif [ -f "$d/Cargo.toml" ]; then echo "$name  ($d) [rust]"; fi; \
    done

# ---- Conventional targets --------------------------------------------------

# Build every example into build/<name> (Go and Rust)
build:
    @mkdir -p build
    @for d in plugins/*/ tools/*/; do \
        name=$(basename "$d"); \
        if [ -f "$d/main.go" ]; then \
            echo "building $name (go)"; \
            go build -o "build/$name" "./$d"; \
        elif [ -f "$d/Cargo.toml" ]; then \
            echo "building $name (rust)"; \
            cargo build --quiet --manifest-path "$d/Cargo.toml"; \
            cp "$d/target/debug/$name" "build/$name"; \
        fi; \
    done

# Run the Go tests (Rust crates: `cargo test` per crate)
test:
    go test ./...

# Run static analysis on the Go sources (Rust crates: `cargo clippy` per crate)
lint:
    go vet ./...

# Format the Go sources (Rust crates: `cargo fmt` per crate)
fmt:
    gofmt -l -w .
