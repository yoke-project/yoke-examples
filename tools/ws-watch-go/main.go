// Command ws-watch-go is a minimal reference Yoke tool: a CLI that CONSUMES a
// running Core over its public Gateway surface (REST login + WebSocket), rather
// than registering as a plugin. It is a scriptable stand-in for a graphical
// panel: it logs in, opens the /ws WebSocket, and prints the live frames Core
// pushes (the "connected" greeting, cached stream snapshots, and stream.data
// updates), decoding each stream payload from base64.
//
// It is the Go member of a family of equivalent ws-watch tools (Go/Rust/Python).
//
// Configuration is via flags, each with a dev-friendly default so it runs against
// a dev Core out of the box:
//
//	--addr      Gateway host:port (dev TCP listener; default localhost:8765)
//	--user      login username (must exist in Core's auth.users)
//	--password  login password
//	--subscribe optional comma-separated categories to subscribe to
//	--json      print raw JSON frames instead of the formatted view
package main

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/gorilla/websocket"
)

func main() {
	log.SetFlags(0)
	log.SetPrefix("ws-watch-go: ")

	addr := flag.String("addr", "localhost:8765", "Gateway host:port (dev TCP listener)")
	user := flag.String("user", "dev", "login username (must exist in Core's auth.users)")
	password := flag.String("password", "dev", "login password")
	subscribe := flag.String("subscribe", "", "comma-separated categories to subscribe to (optional)")
	jsonOut := flag.Bool("json", false, "print raw JSON frames instead of the formatted view")
	flag.Parse()

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	token, err := login(*addr, *user, *password)
	if err != nil {
		log.Fatalf("login: %v", err)
	}
	log.Printf("logged in as %q", *user)

	u := url.URL{Scheme: "ws", Host: *addr, Path: "/ws"}
	header := http.Header{}
	header.Set("Cookie", "yoke_session="+token)

	conn, _, err := websocket.DefaultDialer.DialContext(ctx, u.String(), header)
	if err != nil {
		log.Fatalf("ws dial %s: %v", u.String(), err)
	}
	defer conn.Close()
	log.Printf("connected to %s; Ctrl-C to stop", u.String())

	if *subscribe != "" {
		cats := strings.Split(*subscribe, ",")
		if err := conn.WriteJSON(map[string]interface{}{
			"type":       "subscribe",
			"categories": cats,
		}); err != nil {
			log.Fatalf("subscribe: %v", err)
		}
	}

	// Close the connection when the context is cancelled so ReadMessage unblocks.
	go func() {
		<-ctx.Done()
		_ = conn.WriteControl(
			websocket.CloseMessage,
			websocket.FormatCloseMessage(websocket.CloseNormalClosure, ""),
			time.Now().Add(time.Second),
		)
		_ = conn.Close()
	}()

	for {
		_, data, err := conn.ReadMessage()
		if err != nil {
			if ctx.Err() != nil {
				log.Printf("shutting down")
				return
			}
			log.Fatalf("read: %v", err)
		}
		if *jsonOut {
			fmt.Println(string(data))
			continue
		}
		printFrame(data)
	}
}

// login performs POST /api/v1/auth/login and returns the yoke_session JWT.
func login(addr, user, password string) (string, error) {
	body, _ := json.Marshal(map[string]string{"username": user, "password": password})
	endpoint := "http://" + addr + "/api/v1/auth/login"

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Post(endpoint, "application/json", bytes.NewReader(body))
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("unexpected status %s", resp.Status)
	}
	for _, ck := range resp.Cookies() {
		if ck.Name == "yoke_session" {
			return ck.Value, nil
		}
	}
	return "", fmt.Errorf("no yoke_session cookie in login response")
}

// printFrame renders one WebSocket JSON frame in a compact, human-readable form.
func printFrame(data []byte) {
	var m map[string]interface{}
	if err := json.Unmarshal(data, &m); err != nil {
		fmt.Printf("[?] %s\n", string(data))
		return
	}

	switch m["type"] {
	case "stream.data":
		payload := ""
		if enc, ok := m["payload"].(string); ok {
			if raw, err := base64.StdEncoding.DecodeString(enc); err == nil {
				payload = string(raw)
			} else {
				payload = enc
			}
		}
		fmt.Printf("[stream.data] %v/%v seq=%v: %s\n",
			m["plugin_id"], m["stream_id"], m["sequence"], payload)
	case "connected":
		fmt.Printf("[connected] core_version=%v\n", m["core_version"])
	case "subscribe_ack":
		fmt.Printf("[subscribe_ack] active=%v\n", m["active_categories"])
	default:
		fmt.Printf("[%v] %s\n", m["type"], string(data))
	}
}
