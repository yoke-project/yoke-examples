# yoke-examples

Reference plugins and showcases for the Yoke project. These are programs that
*use* Yoke (via the SDK), not parts of the framework. They double as
runnable, end-to-end checks that the Core and the SDK work together.

This repository is part of the Yoke project. The project-wide context and the
canonical list of repositories live in `yoke-meta`.

## Role in the project

Per `yoke-meta/docs/repo-roles.md` this is a `showcase` repository. It depends
on `yoke-sdk-go` (and transitively `yoke-proto`), resolved locally during
development via `replace` directives in `go.mod`. It does not depend on
`yoke-core` at build time; it exercises a running Core at run time.

## What's here

| Path | What |
| --- | --- |
| `cmd/hello-plugin/` | Minimal reference plugin built on `pluginapi`. |
| `plugins/hello-plugin/manifest.json` | Its manifest (consumed by Core's discovery). |

### hello-plugin

A minimal plugin that demonstrates the full lifecycle against a running Core:

- dials `core.sock` and registers (bootstrap-token auth);
- opens the bidirectional session and sends heartbeats;
- serves a structured stream `hello.tick` that emits a JSON tick once a second
  while the stream is active (Core auto-starts declared streams on session open);
- answers the point-in-time query `hello.echo`.

Configuration is read from the environment the supervisor sets when it launches
a plugin, each with a dev-friendly default:

| Env var | Default | Meaning |
| --- | --- | --- |
| `YOKE_CORE_SOCKET` | `/run/yoke/core.sock` | Core plugin-protocol socket to dial |
| `YOKE_PLUGIN_ID` | `hello-plugin` | plugin identity (must match the manifest) |
| `YOKE_BOOTSTRAP_TOKEN` | `dev` | registration token (any non-empty value is accepted when Core has not issued one) |
| `YOKE_PLUGIN_SOCKET` | — | optional endpoint reported at registration |

## Running it end-to-end (dev)

Against a `yoke-core` checked out as a sibling, using its dev config:

```sh
# 1. install this plugin's manifest where the dev Core discovers it
mkdir -p ../yoke-core/.local/etc/plugins.d/hello-plugin
cp plugins/hello-plugin/manifest.json ../yoke-core/.local/etc/plugins.d/hello-plugin/

# 2. start the Core (from the yoke-core dir)
( cd ../yoke-core && just run )

# 3. build and run the plugin against the Core's socket
just build
YOKE_CORE_SOCKET="$(cd ../yoke-core && pwd)/.local/run/core.sock" \
  ./build/hello-plugin

# 4. observe it from yoke-admin (in another shell, from yoke-core)
( cd ../yoke-core && ./build/yoke-admin --config config/core.dev.yaml plugin show hello-plugin )
```

Expected: the plugin logs `registered … session=…` and `stream hello.tick
started`; `yoke-admin plugin show` reports `runtime_state Streaming` with a
`session_id`, and `plugin lifecycle` shows a `registration.accepted` event.

## Local operations

| Command | Purpose |
| --- | --- |
| `just build` | Build the example binaries |
| `just test` | Run the tests |
| `just lint` | Static analysis (`go vet`) |
| `just fmt` | Format the Go sources |

The conventions are documented in `yoke-meta/docs/justfile-conventions.md`.
