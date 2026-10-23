package prestate

import (
	"errors"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core"
	"github.com/ethereum/go-ethereum/core/state"
	"github.com/ethereum/go-ethereum/core/tracing"
	"github.com/ethereum/go-ethereum/core/vm"
	"math/big"
	"sync"
)

type WatchedStorage struct {
	Account common.Address `json:"account"`
	Slot    common.Hash    `json:"slot"`
}
type EconomicObservationPlan struct {
	Subject       common.Hash      `json:"subject"`
	NativeOrdinal int              `json:"nativeOrdinal"`
	Accounts      []common.Address `json:"accounts"`
	Storage       []WatchedStorage `json:"storage"`
}
type AccountObservation struct {
	Address  common.Address `json:"address"`
	Balance  string         `json:"balance"`
	Nonce    uint64         `json:"nonce"`
	CodeHash common.Hash    `json:"codeHash"`
}
type StorageObservation struct {
	Key   WatchedStorage `json:"key"`
	Value common.Hash    `json:"value"`
}
type StateObservation struct {
	Accounts []AccountObservation `json:"accounts"`
	Storage  []StorageObservation `json:"storage"`
}
type NativeCallObservation struct {
	Depth            int            `json:"depth"`
	Parent           int            `json:"parent"`
	Kind             byte           `json:"kind"`
	From             common.Address `json:"from"`
	To               common.Address `json:"to"`
	Input            hexutil.Bytes  `json:"input"`
	Output           hexutil.Bytes  `json:"output"`
	Reverted         bool           `json:"reverted"`
	AncestorReverted bool           `json:"ancestorReverted"`
	GasUsed          uint64         `json:"gasUsed"`
	Value            *string        `json:"nativeCallValue,omitempty"`
	RulesWordAtEntry *common.Hash   `json:"rulesWordAtEntry,omitempty"`
}
type NativeEconomicObservation struct {
	Plan     EconomicObservationPlan `json:"plan"`
	Before   StateObservation        `json:"beforeFirstArrival"`
	After    StateObservation        `json:"afterBlockFinalizationBeforeCommit"`
	Calls    []NativeCallObservation `json:"subjectCalls"`
	Complete bool                    `json:"complete"`
	Bytes    int                     `json:"callBytes"`
}

func observeState(s *state.StateDB, p EconomicObservationPlan) StateObservation {
	o := StateObservation{}
	for _, a := range p.Accounts {
		o.Accounts = append(o.Accounts, AccountObservation{a, s.GetBalance(a).Dec(), s.GetNonce(a), s.GetCodeHash(a)})
	}
	for _, k := range p.Storage {
		o.Storage = append(o.Storage, StorageObservation{k, s.GetState(k.Account, k.Slot)})
	}
	return o
}

// The pinned Nitro already installs core.ReadyEVMForL2. Chain it, never replace
// its ArbOS processor. This local scientific adapter requires a fresh process
// with no concurrent EVM users. The mutex serializes this adapter's own calls;
// it is not a safe concurrent server API. The prior hook is restored on STOP.
var scientificObservationMu sync.Mutex

func RunHookrObserved(c *Candidate, b *Bridge, i *LPIntervention, p EconomicObservationPlan) (*CalibrationResult, error) {
	return runObservedBlock(c, b, p, func() (*CalibrationResult, error) {
		if i == nil {
			return RunCanonical(c, b)
		}
		return RunHookrBranch(c, b, *i)
	})
}

func runObservedBlock(c *Candidate, b *Bridge, p EconomicObservationPlan, invoke func() (*CalibrationResult, error)) (*CalibrationResult, error) {
	if c == nil || b == nil || b.observation != nil || p.NativeOrdinal < 1 || p.NativeOrdinal >= len(c.block.Transactions()) || p.Subject != c.block.Transactions()[p.NativeOrdinal].Hash() || len(p.Accounts) > 16 || len(p.Storage) > 64 {
		return nil, errors.New("ECONOMIC_OBSERVATION_PLAN_REJECTED")
	}
	scientificObservationMu.Lock()
	defer scientificObservationMu.Unlock()
	observation := &NativeEconomicObservation{Plan: p}
	b.observation = observation
	previous := core.ReadyEVMForL2
	if previous == nil {
		return nil, b.stop("PINNED_NITRO_PROCESSOR_HOOK_MISSING", nil)
	}
	defer func() { core.ReadyEVMForL2 = previous }()
	stack := []int{}
	core.ReadyEVMForL2 = func(evm *vm.EVM, msg *core.Message) {
		previous(evm, msg)
		if msg.Tx == nil || msg.Tx.Hash() != p.Subject {
			return
		}
		if evm.Config.Tracer != nil {
			panic(b.stop("UNEXPECTED_EXISTING_NATIVE_TRACER", nil))
		}
		evm.Config.Tracer = &tracing.Hooks{
			OnEnter: func(depth int, kind byte, from, to common.Address, input []byte, gas uint64, value *big.Int) {
				if len(observation.Calls) >= 4096 || len(input) > 131072 || observation.Bytes+len(input) > 8<<20 {
					panic(b.stop("ECONOMIC_CALL_OBSERVATION_BUDGET", nil))
				}
				if depth != len(stack) {
					panic(b.stop("NATIVE_CALL_DEPTH_INCOMPLETE", nil))
				}
				parent := -1
				if len(stack) > 0 {
					parent = stack[len(stack)-1]
				}
				n := len(observation.Calls)
				observation.Calls = append(observation.Calls, NativeCallObservation{Depth: depth, Parent: parent, Kind: kind, From: from, To: to, Input: common.CopyBytes(input)})
				if value != nil {
					v := value.String()
					observation.Calls[n].Value = &v
				}
				if from == hookrRoot && to == hookrRules {
					v := b.live.GetState(hookrRules, hookrConfigSlot)
					observation.Calls[n].RulesWordAtEntry = &v
					if e := b.live.Error(); e != nil {
						panic(b.stop("QUOTE_CONFIG_OBSERVATION_FAILED", e))
					}
					b.guard()
				}
				stack = append(stack, n)
				observation.Bytes += len(input)
			},
			OnExit: func(depth int, output []byte, gasUsed uint64, err error, reverted bool) {
				if depth != len(stack)-1 {
					panic(b.stop("NATIVE_CALL_EXIT_INCOMPLETE", nil))
				}
				if len(output) > 131072 || observation.Bytes+len(output) > 8<<20 {
					panic(b.stop("ECONOMIC_CALL_OBSERVATION_BUDGET", nil))
				}
				n := stack[len(stack)-1]
				stack = stack[:len(stack)-1]
				observation.Calls[n].Output = common.CopyBytes(output)
				observation.Calls[n].GasUsed = gasUsed
				observation.Calls[n].Reverted = reverted || err != nil
				observation.Bytes += len(output)
				if reverted || err != nil {
					for j := n + 1; j < len(observation.Calls); j++ {
						observation.Calls[j].AncestorReverted = true
					}
				}
			},
		}
	}
	out, err := invoke()
	if err != nil {
		return out, err
	}
	if len(stack) != 0 || len(observation.Calls) == 0 {
		return nil, b.stop("ECONOMIC_NATIVE_TRACE_INCOMPLETE", nil)
	}
	observation.Complete = true
	return out, nil
}
