// Command hello-plugin-go is a minimal reference Yoke plugin built on the Go SDK
// (pluginapi). It is the Go member of a family of equivalent "hello" plugins
// (Go/Rust/Python) that all register the same surface under distinct plugin IDs.
// It demonstrates the full plugin lifecycle against a running Core:
//
//   - dial core.sock and register (bootstrap-token auth)
//   - open the bidirectional session and send heartbeats
//   - serve a structured stream "hello.tick" that emits a JSON tick once a
//     second while Core has started the stream
//   - answer the point-in-time query "hello.echo"
//
// Configuration comes from the environment the supervisor sets when it launches
// a plugin (YOKE_CORE_SOCKET, YOKE_PLUGIN_ID, YOKE_BOOTSTRAP_TOKEN,
// YOKE_PLUGIN_SOCKET); each has a sensible default so the binary can also be run
// by hand against a dev Core.
package main

import (
	"context"
	"encoding/json"
	"log"
	"os"
	"os/signal"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/yoke-project/yoke-sdk-go/pluginapi"
)

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func main() {
	log.SetFlags(log.LstdFlags | log.Lmsgprefix)
	log.SetPrefix("hello-plugin-go: ")

	coreSock := env("YOKE_CORE_SOCKET", "/run/yoke/core.sock")
	pluginID := env("YOKE_PLUGIN_ID", "hello-plugin-go")

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	cfg := pluginapi.RegistrationConfig{
		PluginID:      pluginID,
		PluginVersion: "0.1.0",
		Language:      "go",
		SDKVersion:    "yoke-sdk-go",
		// The supervisor injects a real token; for hand-launched dev runs Core
		// accepts any non-empty token (no token was issued), so default to "dev".
		BootstrapToken: env("YOKE_BOOTSTRAP_TOKEN", "dev"),
		Endpoint:       os.Getenv("YOKE_PLUGIN_SOCKET"),
		PID:            uint32(os.Getpid()),
		Capabilities:   []string{"hello"},
		Streams:        []string{"hello.tick"},
		Commands:       []string{"StartStream", "StopStream"},
	}

	client, err := pluginapi.Dial(ctx, coreSock, cfg)
	if err != nil {
		log.Fatalf("dial %s: %v", coreSock, err)
	}
	defer client.Close()

	if err := client.Register(ctx); err != nil {
		log.Fatalf("register: %v", err)
	}

	// Structured stream: emit a JSON tick every second until Core stops it.
	client.RegisterStreamProducer("hello.tick", "hello", "v1", pluginapi.StreamProducer{
		OnStart: func(ctx context.Context, emitter pluginapi.StreamEmitter) {
			log.Printf("stream hello.tick started")
			ticker := time.NewTicker(time.Second)
			defer ticker.Stop()
			var seq uint64
			for {
				select {
				case <-ctx.Done():
					return
				case t := <-ticker.C:
					seq++
					payload, _ := json.Marshal(map[string]any{
						"seq": seq,
						"ts":  t.UnixMilli(),
						"msg": "hello from " + pluginID,
					})
					if err := emitter.EmitData(payload); err != nil {
						log.Printf("emit: %v", err)
						return
					}
				}
			}
		},
		OnStop: func() { log.Printf("stream hello.tick stopped") },
	})

	// Point-in-time query: echo the params back.
	client.RegisterQueryHandler("hello.echo", func(_ context.Context, queryType string, params []byte) (string, string, []byte, string) {
		out, _ := json.Marshal(map[string]any{
			"query": queryType,
			"echo":  string(params),
		})
		return "hello", "v1", out, ""
	})

	if err := client.OpenSession(ctx); err != nil {
		log.Fatalf("open session: %v", err)
	}

	// Heartbeat loop in the background; report Streaming when a stream is active.
	go func() {
		err := client.RunHeartbeat(ctx, func() (string, uint32, bool) {
			n := client.ActiveStreamCount()
			state := "Idle"
			if n > 0 {
				state = "Streaming"
			}
			return state, n, false
		})
		if err != nil && ctx.Err() == nil {
			log.Printf("heartbeat: %v", err)
		}
	}()

	// Drain any Core-dispatched commands not handled by a stream producer.
	go func() {
		var n atomic.Uint64
		for cmd := range client.Commands() {
			log.Printf("command #%d: type=%s stream=%s", n.Add(1), cmd.Type, cmd.StreamID)
		}
	}()

	log.Printf("registered and running (session=%s); Ctrl-C to stop", client.SessionID)
	<-ctx.Done()
	log.Printf("shutting down")
}
