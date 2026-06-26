module github.com/yoke-project/yoke-examples

go 1.25.0

require (
	github.com/gorilla/websocket v1.5.3
	github.com/yoke-project/yoke-sdk-go v0.0.0
)

require (
	github.com/yoke-project/yoke-proto v0.0.0 // indirect
	golang.org/x/net v0.51.0 // indirect
	golang.org/x/sys v0.42.0 // indirect
	golang.org/x/text v0.34.0 // indirect
	google.golang.org/genproto/googleapis/rpc v0.0.0-20240318140521-94a12d6c2237 // indirect
	google.golang.org/grpc v1.64.0 // indirect
	google.golang.org/protobuf v1.34.1 // indirect
)

// Sibling workspace modules, resolved locally (not published).
replace (
	github.com/yoke-project/yoke-proto => ../yoke-proto
	github.com/yoke-project/yoke-sdk-go => ../yoke-sdk-go
)
