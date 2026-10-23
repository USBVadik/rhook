package prestate

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"math/big"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core/rawdb"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/ethereum/go-ethereum/ethdb"
	"github.com/ethereum/go-ethereum/rlp"
	"github.com/ethereum/go-ethereum/trie"
	"github.com/ethereum/go-ethereum/triedb"
)

type residentProofSource struct {
	checkpoint Checkpoint
	tree       *trie.Trie
	tdb        *triedb.Database
	disk       ethdb.Database
	calls      int
}

func (s *residentProofSource) GetProof(ctx context.Context, c Checkpoint, a common.Address, slots []common.Hash) (*RPCProof, error) {
	s.calls++
	if c != s.checkpoint {
		return nil, errors.New("SYNTHETIC_CHECKPOINT_CHANGED")
	}
	encoded, e := s.tree.Get(crypto.Keccak256(a[:]))
	if e != nil {
		return nil, e
	}
	proof := &RPCProof{Address: a, AccountProof: proofNodes(s.tree, crypto.Keccak256(a[:])), Balance: (*hexutil.Big)(new(big.Int)), StorageHash: types.EmptyRootHash, CodeHash: types.EmptyCodeHash}
	if len(encoded) == 0 {
		for _, k := range slots {
			proof.StorageProof = append(proof.StorageProof, RPCStorageProof{Key: k, Value: (*hexutil.Big)(new(big.Int))})
		}
		return proof, nil
	}
	var account types.StateAccount
	if e = rlp.DecodeBytes(encoded, &account); e != nil {
		return nil, e
	}
	proof.Nonce = hexutil.Uint64(account.Nonce)
	proof.Balance = (*hexutil.Big)(account.Balance.ToBig())
	proof.StorageHash = account.Root
	proof.CodeHash = common.BytesToHash(account.CodeHash)
	if len(slots) == 0 {
		return proof, nil
	}
	st, e := trie.New(trie.StorageTrieID(c.StateRoot, crypto.Keccak256Hash(a[:]), account.Root), s.tdb)
	if e != nil {
		return nil, e
	}
	for _, k := range slots {
		v, e := st.Get(crypto.Keccak256(k[:]))
		if e != nil {
			return nil, e
		}
		n := new(big.Int)
		if len(v) > 0 {
			var content []byte
			if e = rlp.DecodeBytes(v, &content); e != nil {
				return nil, e
			}
			n.SetBytes(content)
		}
		proof.StorageProof = append(proof.StorageProof, RPCStorageProof{Key: k, Value: (*hexutil.Big)(n), Proof: proofNodes(st, crypto.Keccak256(k[:]))})
	}
	return proof, nil
}
func (s *residentProofSource) GetCode(ctx context.Context, c Checkpoint, a common.Address) ([]byte, error) {
	proof, e := s.GetProof(ctx, c, a, nil)
	if e != nil {
		return nil, e
	}
	return rawdb.ReadCode(s.disk, proof.CodeHash), nil
}

func exerciseProspectiveFixture(t *testing.T, c Checkpoint, p BlockPackage, tdb *triedb.Database, disk ethdb.Database, mode string) {
	t.Helper()
	tree, e := trie.New(trie.StateTrieID(c.StateRoot), tdb)
	if e != nil {
		t.Fatal(e)
	}
	source := &residentProofSource{checkpoint: c, tree: tree, tdb: tdb, disk: disk}
	proof, e := source.GetProof(context.Background(), c, addrA, nil)
	if e != nil {
		t.Fatal(e)
	}
	// Remove the contract account leaf and code preimage, retaining all other
	// canonical update siblings. Both missing dependencies must traverse live RPC.
	missing := map[common.Hash]bool{}
	for _, n := range proof.AccountProof {
		var list [][]byte
		if rlp.DecodeBytes(n, &list) == nil && len(list) == 2 && len(list[0]) > 0 && list[0][0]>>4 >= 2 {
			missing[crypto.Keccak256Hash(n)] = true
		}
	}
	if len(missing) == 0 {
		t.Fatal("no standalone account leaf removed")
	}
	var partial []hexutil.Bytes
	for _, n := range p.State {
		if !missing[crypto.Keccak256Hash(n)] {
			partial = append(partial, n)
		}
	}
	p.State = partial
	var codes []hexutil.Bytes
	for _, code := range p.Codes {
		if crypto.Keccak256Hash(code) != proof.CodeHash {
			codes = append(codes, code)
		}
	}
	p.Codes = codes
	var header map[string]json.RawMessage
	json.Unmarshal(p.Block, &header)
	var txs []map[string]any
	rawByHash := map[common.Hash]hexutil.Bytes{}
	for _, raw := range p.Raw {
		tx := new(types.Transaction)
		encoded := []byte(raw)
		if raw[0] <= 0x7f {
			encoded, _ = rlp.EncodeToBytes([]byte(raw))
		}
		if e = rlp.DecodeBytes(encoded, tx); e != nil {
			t.Fatal(e)
		}
		txs = append(txs, map[string]any{"hash": tx.Hash(), "type": hexutil.Uint64(tx.Type())})
		rawByHash[tx.Hash()] = raw
	}
	header["transactions"], _ = json.Marshal(txs)
	p.Block, _ = json.Marshal(header)
	nativeEntered := false
	failedTransportCalls := 0
	liveCodeCalls := 0
	liveProofCalls := 0
	var beforeNativeCalls uint64
	client := &http.Client{Transport: roundTripFunc(func(q *http.Request) (*http.Response, error) {
		var req struct {
			ID     uint64            `json:"id"`
			Method string            `json:"method"`
			Params []json.RawMessage `json:"params"`
		}
		json.NewDecoder(q.Body).Decode(&req)
		if nativeEntered && (mode == "unavailable") {
			failedTransportCalls++
			return &http.Response{StatusCode: 503, Body: io.NopCloser(strings.NewReader(`{"error":"synthetic unavailable"}`))}, nil
		}
		var result any
		switch req.Method {
		case "eth_chainId":
			result = "0x1237"
		case "eth_getBlockByNumber":
			var number string
			json.Unmarshal(req.Params[0], &number)
			if number == "latest" || number == hexutil.EncodeUint64(c.BlockNumber) {
				result = p.Parent
			} else if number == hexutil.EncodeUint64(c.BlockNumber+1) {
				result = p.Block
			} else {
				t.Fatalf("unexpected selected number %s", number)
			}
		case "eth_getRawTransactionByHash":
			var hash common.Hash
			json.Unmarshal(req.Params[0], &hash)
			result = rawByHash[hash]
		case "debug_executionWitness":
			result = map[string]any{"state": p.State, "codes": p.Codes}
		case "eth_getProof":
			var a common.Address
			var keys []common.Hash
			var height string
			json.Unmarshal(req.Params[0], &a)
			json.Unmarshal(req.Params[1], &keys)
			json.Unmarshal(req.Params[2], &height)
			if height != hexutil.EncodeUint64(c.BlockNumber) {
				t.Fatal("latest/different root used")
			}
			x, e := source.GetProof(q.Context(), c, a, keys)
			if e != nil {
				t.Fatal(e)
			}
			if nativeEntered {
				liveProofCalls++
				if mode == "wrong-root" {
					x.AccountProof = []hexutil.Bytes{{0xc0}}
				}
			}
			result = x
		case "eth_getCode":
			var a common.Address
			var height string
			json.Unmarshal(req.Params[0], &a)
			json.Unmarshal(req.Params[1], &height)
			if height != hexutil.EncodeUint64(c.BlockNumber) {
				t.Fatal("code root changed")
			}
			x, e := source.GetCode(q.Context(), c, a)
			if e != nil {
				t.Fatal(e)
			}
			result = hexutil.Bytes(x)
			if nativeEntered && mode == "bad-code" {
				result = hexutil.Bytes{0xff}
			}
			if nativeEntered {
				liveCodeCalls++
			}
		default:
			t.Fatalf("unexpected RPC %s", req.Method)
		}
		body, _ := json.Marshal(map[string]any{"jsonrpc": "2.0", "id": req.ID, "result": result})
		return &http.Response{StatusCode: 200, ContentLength: int64(len(body)), Body: io.NopCloser(strings.NewReader(string(body)))}, nil
	})}
	rpc, e := NewRPCSource("https://example.invalid/v2/synthetic-secret", client, 8<<20, 32<<20)
	if e != nil {
		t.Fatal(e)
	}
	evidence := map[string][]byte{}
	write := func(name string, b []byte) error {
		if _, ok := evidence[name]; ok {
			t.Fatal("evidence overwritten")
		}
		evidence[name] = append([]byte(nil), b...)
		return nil
	}
	rpc.Configure(64, time.Now().Add(time.Minute), nil)
	emit := func(event string, value any) error {
		if event == "NATIVE_REPLAY_ENTERED" {
			nativeEntered = true
			_, _, beforeNativeCalls, _ = rpc.Transcript()
			if len(evidence["INPUT_PRECOMMIT.json"]) == 0 || len(evidence["BLOCK_PACKAGE.json"]) == 0 {
				t.Fatal("native entered before durable input precommit")
			}
		}
		return nil
	}
	out := RunProspective(context.Background(), rpc, write, emit, func(time.Duration) {}, time.Now().Add(time.Minute))
	if out.NativeAttempts != 1 {
		t.Fatalf("native never entered: %+v", out)
	}
	if mode == "success" {
		if out.Terminal != "CANONICAL_ACTUAL_ROOTS_MATCH" || out.Native == nil || !out.Native.Matched {
			t.Fatalf("full native live hydration: %+v", out)
		}
		if liveProofCalls == 0 || liveCodeCalls == 0 || out.RpcRequests <= beforeNativeCalls {
			t.Fatal("no live proof/code hydration")
		}
		if !out.FinalWitnessComplete || out.InitialWitnessCommitment == out.FinalWitnessCommitment {
			t.Fatal("dynamic witness falsely pre-frozen")
		}
		commit, _, _, _ := rpc.Transcript()
		if commit != out.RpcTranscriptCommitment {
			t.Fatal("transcript not deterministic")
		}
	} else {
		if mode == "wrong-root" && !strings.Contains(out.Cause, "PROOF_AUTHENTICATION_FAILED") {
			t.Fatal(out.Cause)
		}
		if mode == "bad-code" && !strings.Contains(out.Cause, "CODE_PREIMAGE_HASH_MISMATCH") {
			t.Fatal(out.Cause)
		}
		if out.Terminal == "CANONICAL_ACTUAL_ROOTS_MATCH" || out.FinalWitnessComplete {
			t.Fatal("host failure accepted")
		}
		if mode == "unavailable" && (out.Terminal != "HOST_STOP_MISSING_STATE" || failedTransportCalls != 1) {
			t.Fatalf("unavailable retried/reclassified: %+v calls=%d", out, failedTransportCalls)
		}
	}
	if len(evidence["FINAL_WITNESS.json"]) == 0 || len(evidence["RPC_TRANSCRIPT.json"]) == 0 {
		t.Fatal("missing failure/success material seal")
	}
}
