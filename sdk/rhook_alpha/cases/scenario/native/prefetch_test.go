package scenario

import (
	"bufio"
	"encoding/json"
	"net"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/ethereum/go-ethereum/common"
	prestate "local/rhook-robinhood"
)

// Characterize the retained bridge, without ProduceBlock or any EVM execution:
// fetching an original-root path must preserve an already-written overlay.
func TestOriginalRootPrefetchPreservesOverlayWrite(t *testing.T) {
	directory := os.Getenv("RHOOK_PREFETCH_WRITE_FIXTURE")
	if directory == "" {
		t.Skip("private authenticated fixture not shipped with source")
	}
	raw, err := os.ReadFile(filepath.Join(directory, "READ_AFTER_WRITE_SCENARIO.json"))
	if err != nil {
		t.Fatal(err)
	}
	proofBytes, err := os.ReadFile(filepath.Join(directory, "READ_AFTER_WRITE_PROOF.json"))
	if err != nil {
		t.Fatal(err)
	}
	var proof prestate.RPCProof
	if err = json.Unmarshal(proofBytes, &proof); err != nil {
		t.Fatal(err)
	}
	if len(proof.StorageProof) != 1 {
		t.Fatal("fixture scope")
	}
	spec, err := Parse(raw)
	if err != nil {
		t.Fatal(err)
	}
	tmp, err := os.MkdirTemp("/private/tmp", "rhc-pf-")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmp)
	socket := filepath.Join(tmp, "b.sock")
	listener, err := net.Listen("unix", socket)
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	done := make(chan error, 1)
	go func() {
		connection, err := listener.Accept()
		if err != nil {
			done <- err
			return
		}
		defer connection.Close()
		connection.SetDeadline(time.Now().Add(3 * time.Second))
		line, err := bufio.NewReader(connection).ReadBytes('\n')
		if err != nil {
			done <- err
			return
		}
		var q struct {
			ID         int                 `json:"id"`
			Kind       string              `json:"kind"`
			Address    common.Address      `json:"address"`
			Slots      []common.Hash       `json:"slots"`
			Checkpoint prestate.Checkpoint `json:"checkpoint"`
		}
		if err = json.Unmarshal(line, &q); err != nil {
			done <- err
			return
		}
		if q.Kind != "eth_getProof" || q.Address != proof.Address || len(q.Slots) != 1 || q.Checkpoint != spec.Checkpoint {
			done <- os.ErrInvalid
			return
		}
		done <- json.NewEncoder(connection).Encode(map[string]any{"id": q.ID, "result": proof})
	}()
	source := &discoverySource{socket: socket, checkpoint: spec.Checkpoint, deadline: time.Now().Add(5 * time.Second)}
	a, err := admitWithSource(raw, officialProfile(), source)
	if err != nil {
		t.Fatal(err)
	}
	bridge, err := openBridge(a.input)
	if err != nil {
		t.Fatal(err)
	}
	defer prestate.CloseScenarioBridge(bridge)
	state, err := bridge.State()
	if err != nil {
		t.Fatal(err)
	}
	key := a.input.profile.ConfigSlot
	original := spec.Configs.Baseline[0]
	variant := spec.Configs.Variant[0]
	err = bridge.Protect(func() error {
		if state.GetState(rulesAddress, key) != original {
			t.Fatal("original config")
		}
		state.SetState(rulesAddress, key, variant)
		got := state.GetState(proof.Address, proof.StorageProof[0].Key)
		if got.Big().Cmp(proof.StorageProof[0].Value.ToInt()) != 0 {
			t.Fatal("original-root value")
		}
		if state.GetState(rulesAddress, key) != variant {
			t.Fatal("overlay reset by prefetch")
		}
		return state.Error()
	})
	if err != nil {
		t.Fatal(err)
	}
	if err = <-done; err != nil {
		t.Fatal(err)
	}
	other, err := openBridge(a.input)
	if err != nil {
		t.Fatal(err)
	}
	defer prestate.CloseScenarioBridge(other)
	err = other.Protect(func() error {
		st, err := other.State()
		if err != nil {
			return err
		}
		if st.GetState(rulesAddress, key) != original {
			t.Fatal("overlay leaked to independent world")
		}
		return st.Error()
	})
	if err != nil {
		t.Fatal(err)
	}
}
