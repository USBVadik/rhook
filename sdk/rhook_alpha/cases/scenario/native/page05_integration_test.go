package scenario

import (
	"bytes"
	"context"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"

	"github.com/ethereum/go-ethereum/common"
	prestate "local/rhook-robinhood"
)

// Exercise the installed JS broker and the actual Bridge without ProduceBlock.
func TestPage05BrokerPreservesOverlayAndIndependentNilSource(t *testing.T) {
	fixture, lib, scenario, state := os.Getenv("RHOOK_PAGE05_BROKER"), os.Getenv("RHOOK_PAGE05_LIB"), os.Getenv("RHOOK_PAGE05_SCENARIO"), os.Getenv("RHOOK_PAGE05_STATE")
	if fixture == "" || lib == "" || scenario == "" || state == "" {
		t.Skip("private authenticated page05 fixture not provided")
	}
	raw, err := os.ReadFile(scenario)
	if err != nil {
		t.Fatal(err)
	}
	spec, err := Parse(raw)
	if err != nil {
		t.Fatal(err)
	}
	tmp, err := os.MkdirTemp("/private/tmp", "rhc-pg5-")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmp)
	socket, ready, result := filepath.Join(tmp, "b.sock"), filepath.Join(tmp, "ready.json"), filepath.Join(tmp, "result.json")
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, "/usr/local/bin/node", fixture, socket, ready, result)
	cmd.Env = []string{"PATH=/usr/bin:/bin:/usr/sbin:/sbin", "LANG=C", "TZ=UTC", "RHOOK_PAGE05_LIB=" + lib, "RHOOK_PAGE05_SCENARIO=" + scenario, "RHOOK_PAGE05_STATE=" + state}
	var output bytes.Buffer
	cmd.Stdout = &output
	cmd.Stderr = &output
	if err = cmd.Start(); err != nil {
		t.Fatal(err)
	}
	waited := false
	defer func() {
		if !waited {
			cancel()
			_ = cmd.Wait()
		}
	}()
	for i := 0; i < 400; i++ {
		if _, err = os.Stat(ready); err == nil {
			break
		}
		time.Sleep(5 * time.Millisecond)
	}
	if _, err = os.Stat(ready); err != nil {
		t.Fatalf("broker ready: %v; %s", err, output.String())
	}
	var expected struct {
		Address common.Address `json:"address"`
		Key     common.Hash    `json:"key"`
		Value   string         `json:"value"`
	}
	data, err := os.ReadFile(result + ".expected")
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(data, &expected); err != nil {
		t.Fatal(err)
	}
	source := &discoverySource{socket: socket, checkpoint: spec.Checkpoint, deadline: time.Now().Add(5 * time.Second)}
	admitted, err := admitWithSource(raw, officialProfile(), source)
	if err != nil {
		t.Fatal(err)
	}
	bridge, err := openBridge(admitted.input)
	if err != nil {
		t.Fatal(err)
	}
	defer prestate.CloseScenarioBridge(bridge)
	key := admitted.input.profile.ConfigSlot
	original, variant := spec.Configs.Baseline[0], spec.Configs.Variant[0]
	err = bridge.Protect(func() error {
		st, e := bridge.State()
		if e != nil {
			return e
		}
		if st.GetState(rulesAddress, key) != original {
			t.Fatal("original LP")
		}
		st.SetState(rulesAddress, key, variant)
		if st.GetState(expected.Address, expected.Key).Big().String() != expected.Value {
			t.Fatal("lazy original-root value")
		}
		if st.GetState(rulesAddress, key) != variant {
			t.Fatal("page reset overlay")
		}
		return st.Error()
	})
	if err != nil {
		t.Fatal(err)
	}
	second, err := openBridge(admitted.input)
	if err != nil {
		t.Fatal(err)
	}
	defer prestate.CloseScenarioBridge(second)
	err = second.Protect(func() error {
		st, e := second.State()
		if e != nil {
			return e
		}
		if st.GetState(rulesAddress, key) != original {
			t.Fatal("overlay leaked to second world")
		}
		if st.GetState(expected.Address, expected.Key).Big().String() != expected.Value {
			t.Fatal("second original-root value")
		}
		return st.Error()
	})
	if err != nil {
		t.Fatal(err)
	}
	if err = source.finish(ctx); err != nil {
		t.Fatal(err)
	}
	if err = cmd.Wait(); err != nil {
		t.Fatalf("broker completion: %v %s", err, output.String())
	}
	waited = true
	var measured struct {
		Calls     int             `json:"calls"`
		Pages     int             `json:"pages"`
		ProofKeys [][]common.Hash `json:"proofKeys"`
		RPC       int             `json:"RPC"`
		EVM       int             `json:"EVM"`
	}
	data, err = os.ReadFile(result)
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(data, &measured); err != nil {
		t.Fatal(err)
	}
	if measured.Calls != 1 || measured.Pages != 1 || len(measured.ProofKeys) != 1 || len(measured.ProofKeys[0]) != 8 || measured.RPC != 0 || measured.EVM != 0 {
		t.Fatalf("page scope: %s", data)
	}
	// The broker is now closed. A freshly admitted copy with nil Source must read
	// the sealed original material without depending on either live bridge.
	closed, err := os.ReadFile(result + ".closed-input")
	if err != nil {
		t.Fatal(err)
	}
	offline, err := admitWithSource(closed, officialProfile(), nil)
	if err != nil {
		t.Fatal(err)
	}
	third, err := openBridge(offline.input)
	if err != nil {
		t.Fatal(err)
	}
	defer prestate.CloseScenarioBridge(third)
	err = third.Protect(func() error {
		st, e := third.State()
		if e != nil {
			return e
		}
		if st.GetState(rulesAddress, key) != original {
			t.Fatal("nil-Source original LP")
		}
		if st.GetState(expected.Address, expected.Key).Big().String() != expected.Value {
			t.Fatal("nil-Source missing page")
		}
		return st.Error()
	})
	if err != nil {
		t.Fatal(err)
	}
}
