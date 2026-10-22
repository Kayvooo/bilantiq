// Standard entrypoint documented by caddyserver/caddy/cmd/caddy/main.go.
// Only the compiler and the x/net dependency are patched in the Docker build.
package main

import (
	_ "time/tzdata"

	caddycmd "github.com/caddyserver/caddy/v2/cmd"
	_ "github.com/caddyserver/caddy/v2/modules/standard"
)

func main() {
	caddycmd.Main()
}
