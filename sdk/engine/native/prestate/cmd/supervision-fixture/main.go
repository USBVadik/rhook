// Harmless fixture: stdlib and the same supervision package only. No network,
// EVM, RPC credentials, chain data or scientific execution is compiled here.
package main

import (
	"encoding/json"
	"fmt"
	"local/rhook-robinhood/internal/controllersafety"
	"os"
	"strconv"
	"time"
)

func main() {
	if len(os.Args) != 2 {
		os.Exit(2)
	}
	fd, e := strconv.Atoi(os.Getenv("RHOOK_SUPERVISION_FD"))
	if e != nil {
		os.Exit(2)
	}
	stop, e := controllersafety.Start(fd, controllersafety.Timeout, func(reason string) { fmt.Fprintln(os.Stderr, "FIXTURE_CONTROLLER_LOST_"+reason); os.Exit(76) })
	if e != nil {
		os.Exit(2)
	}
	defer stop()
	if os.Getenv("RHOOK_FIXTURE_PHASE") == "simulated-native" {
		json.NewEncoder(os.Stdout).Encode(map[string]any{"event": "NATIVE_REPLAY_ENTERED", "fixtureOnly": true})
	}
	f, e := os.OpenFile(os.Args[1], os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600)
	if e != nil {
		os.Exit(2)
	}
	defer f.Close()
	for {
		if _, e = f.WriteString("HARmless_FIXTURE_TICK_NO_RPC_OR_EVM\n"); e != nil {
			os.Exit(2)
		}
		f.Sync()
		time.Sleep(25 * time.Millisecond)
	}
}
