# yoke-examples — repository justfile
#
# Reference plugins and showcases (role: showcase). Conventional targets per
# yoke-meta/docs/justfile-conventions.md. The Yoke SDK is resolved locally via
# the replace directives in go.mod.

set shell := ["bash", "-euo", "pipefail", "-c"]

# ---- Default ---------------------------------------------------------------

# List available recipes
default:
    @just --list

# ---- Conventional targets --------------------------------------------------

# Build the example binaries
build:
    go build -o build/hello-plugin ./cmd/hello-plugin

# Run the tests
test:
    go test ./...

# Run static analysis
lint:
    go vet ./...

# Format the Go sources
fmt:
    gofmt -l -w .
