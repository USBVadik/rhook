package scenario

import (
	"bufio"
	"context"
	"encoding/json"
	"math/big"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/ethereum/go-ethereum/rlp"
	"github.com/holiman/uint256"
	"github.com/offchainlabs/nitro/arbos/burn"
	"github.com/offchainlabs/nitro/arbos/storage"
	prestate "local/rhook-robinhood"
)

func TestLocalDiscoveryAuthenticatesThenReopensWithNilSource(t *testing.T) {
	address := common.HexToAddress("0x1234")
	code := []byte{0x00}
	account := types.StateAccount{Nonce: 1, Balance: uint256.NewInt(5), Root: types.EmptyRootHash, CodeHash: crypto.Keccak256(code)}
	value, err := rlp.EncodeToBytes(&account)
	if err != nil {
		t.Fatal(err)
	}
	node, err := rlp.EncodeToBytes([]any{append([]byte{0x20}, crypto.Keccak256(address[:])...), value})
	if err != nil {
		t.Fatal(err)
	}
	cp := prestate.Checkpoint{ChainID: 4663, BlockNumber: 1, BlockHash: common.HexToHash("0x1"), StateRoot: crypto.Keccak256Hash(node)}
	dir, e := os.MkdirTemp("/private/tmp", "rhc-go-")
	if e != nil {
		t.Fatal(e)
	}
	defer os.RemoveAll(dir)
	socket := filepath.Join(dir, "b.sock")
	listener, e := net.Listen("unix", socket)
	if e != nil {
		t.Fatal(e)
	}
	defer listener.Close()
	done := make(chan error, 1)
	go func() {
		for i := 1; i <= 2; i++ {
			connection, err := listener.Accept()
			if err != nil {
				done <- err
				return
			}
			connection.SetDeadline(time.Now().Add(time.Second))
			raw, err := bufio.NewReaderSize(connection, 65536).ReadSlice('\n')
			if err != nil {
				done <- err
				connection.Close()
				return
			}
			var q map[string]any
			json.Unmarshal(raw, &q)
			var result any
			if q["kind"] == "eth_getProof" {
				result = &prestate.RPCProof{Address: address, AccountProof: []hexutil.Bytes{node}, Nonce: 1, Balance: (*hexutil.Big)(big.NewInt(5)), StorageHash: types.EmptyRootHash, CodeHash: crypto.Keccak256Hash(code), StorageProof: []prestate.RPCStorageProof{}}
			} else {
				result = hexutil.Bytes(code)
			}
			err = json.NewEncoder(connection).Encode(map[string]any{"id": i, "result": result})
			connection.Close()
			if err != nil {
				done <- err
				return
			}
		}
		done <- nil
	}()
	source := &discoverySource{socket: socket, checkpoint: cp, deadline: time.Now().Add(5 * time.Second)}
	budget := prestate.Budget{MaxRequests: 8, MaxBytes: 1 << 20, MaxResponseBytes: 1 << 20, ExpiresAt: source.deadline}
	b, e := prestate.NewBridge(cp, budget, source.bind(Baseline, func() string { return "fixture" }))
	if e != nil {
		t.Fatal(e)
	}
	defer b.Close()
	prestate.ObserveScenarioBridge(b, func(row prestate.ScenarioAccess) { source.record(Baseline, "fixture", row) })
	e = b.Protect(func() error {
		s, e := b.State()
		if e != nil {
			return e
		}
		if s.GetBalance(address).Uint64() != 5 || string(s.GetCode(address)) != string(code) {
			t.Fatal("wrong original state")
		}
		return s.Error()
	})
	if e != nil {
		t.Fatal(e)
	}
	if e = <-done; e != nil {
		t.Fatal(e)
	}
	if source.calls != 2 || len(source.rows) == 0 {
		t.Fatal("source/attribution missing")
	}
	_, raw, e := b.Seal()
	if e != nil {
		t.Fatal(e)
	}
	var witness struct {
		Nodes map[common.Hash]hexutil.Bytes
		Codes map[common.Hash]hexutil.Bytes
	}
	// Seal encodes []byte as base64, so decode with its actual wire type.
	var wire struct {
		Nodes map[common.Hash][]byte
		Codes map[common.Hash][]byte
	}
	if e = json.Unmarshal(raw, &wire); e != nil {
		t.Fatal(e)
	}
	witness.Nodes = map[common.Hash]hexutil.Bytes{}
	witness.Codes = map[common.Hash]hexutil.Bytes{}
	for h, v := range wire.Nodes {
		witness.Nodes[h] = v
	}
	for h, v := range wire.Codes {
		witness.Codes[h] = v
	}
	offline, e := prestate.NewBridge(cp, budget, nil)
	if e != nil {
		t.Fatal(e)
	}
	defer offline.Close()
	if e = offline.LoadWitness(cp, witness.Nodes, witness.Codes); e != nil {
		t.Fatal(e)
	}
	e = offline.Protect(func() error {
		s, e := offline.State()
		if e != nil {
			return e
		}
		if s.GetBalance(address).Uint64() != 5 || string(s.GetCode(address)) != string(code) {
			t.Fatal("offline differed")
		}
		return s.Error()
	})
	if e != nil {
		t.Fatal(e)
	}
	wrong := cp
	wrong.BlockNumber++
	if _, e = source.bind(Baseline, func() string { return "fixture" }).GetCode(context.Background(), wrong, address); e == nil {
		t.Fatal("wrong root context")
	}
}

func TestFilterSlotMatchesPinnedNitroKVStorage(t *testing.T) {
	db := storage.NewMemoryBackedStateDB()
	kv := storage.KVStorage(db, burn.NewSystemBurner(nil, false), types.FilteredTransactionsStateAddress)
	for _, h := range []common.Hash{common.HexToHash("0x662082f787950e94cc829ba1f8c903107b37d0e56f6beb7b258e87a0f0d5b850"), common.HexToHash("0x01"), common.HexToHash("0xff")} {
		if got := transactionFilterSlot(h); got != kv.GetStorageSlot(h) {
			t.Fatalf("Nitro mapping %s", got)
		}
	}
	want := common.HexToHash("0x8f5282fa5f3912b74832adfa2b019a21029f46fd80046984a2bdbb15be0f2c50")
	if transactionFilterSlot(common.HexToHash("0x662082f787950e94cc829ba1f8c903107b37d0e56f6beb7b258e87a0f0d5b850")) != want {
		t.Fatal("saved failure mismatch")
	}
}
func TestDiscoveryCannotUseUnboundSocket(t *testing.T) {
	cp := prestate.Checkpoint{}
	for _, b := range []map[string]any{{}, {"discoveryProfile": DiscoveryProfile, "discoverySocket": "/tmp/other.sock"}, {"discoveryProfile": "wrong", "discoverySocket": "/tmp/closure/broker.sock"}} {
		if _, e := discoveryFor("/tmp/closure/discovery", b, cp); e == nil {
			t.Fatal("unbound discovery")
		}
	}
	if _, e := discoveryFor("/tmp/closure/discovery", map[string]any{"discoveryProfile": DiscoveryProfile, "discoverySocket": "/tmp/closure/broker.sock"}, cp); e != nil {
		t.Fatal(e)
	}
}
func TestSavedCheckpointStopsBeforeProducerOnFilterGap(t *testing.T) {
	path := os.Getenv("RHOOK_SAVED_SCENARIO_REGRESSION")
	if path == "" {
		t.Skip("private saved-root fixture not shipped with source")
	}
	raw, e := os.ReadFile(path)
	if e != nil {
		t.Fatal(e)
	}
	_, e = Admit(raw)
	if e == nil || !strings.Contains(e.Error(), "TRANSACTION_FILTER_PRECONDITION") || !strings.Contains(e.Error(), "8f5282fa5f3912b74832adfa2b019a21029f46fd80046984a2bdbb15be0f2c50") {
		t.Fatalf("exact original-root gap: %v", e)
	}
}
