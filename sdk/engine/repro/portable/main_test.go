package main

import (
	"encoding/json"
	"testing"
	"time"
)

// No test opens the saved block or invokes an EVM, sensor or provider.
func TestPortableAuthorityRejectsMissingAndWrongScope(t *testing.T) {
	b := portableBinding{Operation: "new-operation", Binary: "binary", Plan: digest(planBytes), Package: "/input.json", Output: "/fresh"}
	a := portableAuthority{Approved: true, Domain: "PORTABLE_SAVED_PAIR03", Operation: b.Operation,
		Binary: b.Binary, Package: b.Package, Output: b.Output, Expires: 1200,
		NotBefore: 990, NoRetry: true, MacReady: true, Context: "require_escalated"}
	a.Maximum.ACTUAL, a.Maximum.BRANCH = 1, 1
	if e := checkAuthority(a, b, "/fresh", "binary", time.Unix(1000, 0)); e != nil {
		t.Fatal(e)
	}
	for _, change := range []func(*portableAuthority){
		func(x *portableAuthority) { x.Approved = false },
		func(x *portableAuthority) { x.Domain = "OLD_GRANT" },
		func(x *portableAuthority) { x.Expires = 1000 },
		func(x *portableAuthority) { x.Package = "https://provider.invalid" },
		func(x *portableAuthority) { x.Output = "/used" },
		func(x *portableAuthority) { x.RPC = 1 },
		func(x *portableAuthority) { x.WSS = 1 },
		func(x *portableAuthority) { x.Maximum.ACTUAL = 2 },
		func(x *portableAuthority) { x.Maximum.B = 1 },
		func(x *portableAuthority) { x.NoRetry = false },
	} {
		bad := a
		change(&bad)
		if checkAuthority(bad, b, "/fresh", "binary", time.Unix(1000, 0)) == nil {
			t.Fatal("bad authority accepted")
		}
	}
}

func TestPortablePlanHasNoPackagePathAndPinsAllArrivals(t *testing.T) {
	var x struct {
		Path     string   `json:"packagePath"`
		Arrivals []string `json:"arrivals"`
	}
	if e := json.Unmarshal(planBytes, &x); e != nil {
		t.Fatal(e)
	}
	if x.Path != "" || len(x.Arrivals) != 7 || x.Arrivals[3] != loadPlan().Subject.Hex() {
		t.Fatal("portable plan identity")
	}
}

func TestPortableRejectsBadPackageBeforeFactory(t *testing.T) {
	if _, e := checkedFresh([]byte(`{}`), loadPlan()); e == nil {
		t.Fatal("bad package admitted")
	}
}
