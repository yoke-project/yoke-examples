# tools

Standalone command-line tools that *consume* a running Yoke Core over its
public surfaces — primarily the Gateway's REST + WebSocket API. They play the
role a graphical panel would, but as scriptable CLIs: connect, subscribe to
live streams and lifecycle events, and render them in the terminal.

Each tool lives in its own directory with a `main.go` (one binary per
subdirectory):

```
tools/
└── <tool-name>/
    └── main.go
```

`just build` discovers every `tools/<name>/main.go` automatically and emits
`build/<name>`. Add a new tool by creating a new subdirectory — no justfile
change required.

Like the plugins, these depend on `yoke-sdk-go` (and transitively
`yoke-proto`), resolved locally via the `replace` directives in the
repository `go.mod`. They do not depend on `yoke-core` at build time; they
exercise a running Core at run time.
