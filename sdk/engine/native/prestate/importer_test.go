package prestate

import (
	"encoding/json"
	"math/big"
	"os"
	"testing"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/trie"
	"github.com/offchainlabs/nitro/arbos"
)

func configBytes(t *testing.T) []byte {
	t.Helper()
	v, e := os.ReadFile("testdata/chain-config.json")
	if e != nil {
		t.Fatal(e)
	}
	return v
}
func inputFixture(t *testing.T) (Checkpoint, []byte, []byte, []hexutil.Bytes) {
	t.Helper()
	p := &types.Header{UncleHash: types.EmptyUncleHash, Root: common.HexToHash("0x123"), Difficulty: big.NewInt(1), Number: big.NewInt(123), GasLimit: 32000000, Time: 100, BaseFee: big.NewInt(100000000), Extra: make([]byte, 32)}
	(types.HeaderInfo{ArbOSFormatVersion: 61, L1BlockNumber: 44}).UpdateHeaderWithInfo(p)
	h := types.CopyHeader(p)
	h.Number = big.NewInt(124)
	h.ParentHash = p.Hash()
	h.Time = 101
	h.Root = common.HexToHash("0x456")
	h.ReceiptHash = types.EmptyReceiptsHash
	system := types.NewTx(arbos.InternalTxStartBlock(big.NewInt(4663), big.NewInt(100), 44, h, p))
	h.TxHash = types.DeriveSha(types.Transactions{system}, trie.NewStackTrie(nil))
	marshal := func(h *types.Header, txs []common.Hash) []byte {
		raw, _ := json.Marshal(h)
		var m map[string]any
		json.Unmarshal(raw, &m)
		m["hash"] = h.Hash()
		m["transactions"] = txs
		v, _ := json.Marshal(m)
		return v
	}
	raw, _ := system.MarshalBinary()
	return Checkpoint{4663, 123, p.Hash(), p.Root}, marshal(p, nil), marshal(h, []common.Hash{system.Hash()}), []hexutil.Bytes{raw}
}
func TestCompleteSystemInputAdmission(t *testing.T) {
	c, p, h, tx := inputFixture(t)
	candidate, e := ImportBlock(c, p, h, tx, configBytes(t))
	if e != nil {
		t.Fatal(e)
	}
	if candidate.InputCommitment() == "" {
		t.Fatal("no immutable input commitment")
	}
	if len(candidate.block.Transactions()) != 1 || candidate.block.Transactions()[0].Type() != 0x6a {
		t.Fatal("system input lost")
	}
}
func TestOmittedOrChangedSystemEnvelopeRejected(t *testing.T) {
	c, p, h, tx := inputFixture(t)
	for _, raw := range [][]hexutil.Bytes{nil, {{0x6a, 0xc0}}, append(tx, tx[0])} {
		if _, e := ImportBlock(c, p, h, raw, configBytes(t)); e == nil {
			t.Fatal("incomplete ordered block accepted")
		}
	}
}
func TestWrongChainConfigRejected(t *testing.T) {
	for _, fromTo := range [][2]string{{"4663", "1"}, {"98304", "24576"}, {"196608", "49152"}} {
		raw := string(configBytes(t))
		changed := []byte(replaceOnce(raw, fromTo[0], fromTo[1]))
		if _, e := ValidateConfig(changed, 61); e == nil {
			t.Fatalf("unsupported config %v accepted", fromTo)
		}
	}
	if _, e := ValidateConfig(configBytes(t), 60); e == nil {
		t.Fatal("wrong active ArbOS accepted")
	}
}
func TestHeaderIdentityAndParentRootRejected(t *testing.T) {
	c, p, h, tx := inputFixture(t)
	c.StateRoot = common.HexToHash("0x999")
	if _, e := ImportBlock(c, p, h, tx, configBytes(t)); e == nil {
		t.Fatal("wrong checkpoint")
	}
}
func replaceOnce(s, old, new string) string {
	for i := 0; i+len(old) <= len(s); i++ {
		if s[i:i+len(old)] == old {
			return s[:i] + new + s[i+len(old):]
		}
	}
	return s
}
