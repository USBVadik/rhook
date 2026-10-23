// Read-only offline admission command; contains no native replay invocation.
package main

import (
	"encoding/json"
	"fmt"
	prestate "local/rhook-robinhood"
	"os"
)

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "one block package file required")
		os.Exit(2)
	}
	raw, e := os.ReadFile(os.Args[1])
	if e != nil {
		fmt.Fprintln(os.Stderr, "INPUT_READ_FAILURE")
		os.Exit(2)
	}
	_, inventory, e := prestate.AdmitPackage(raw)
	if e == nil {
		e = prestate.CheckHookrBindings(raw)
	}
	if e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(1)
	}
	json.NewEncoder(os.Stdout).Encode(inventory)
}
