package scenario

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"net"
	"path/filepath"
	"sync"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	prestate "local/rhook-robinhood"
)

const DiscoveryProfile = "rhook/scenario-witness-discovery/0.1"

// This source can reach only the operation's private local socket. The broker
// owns credentials and the shared acquisition budget; Bridge verifies replies
// again before adding original-root trie nodes to a live world.
type discoverySource struct {
	mu         sync.Mutex
	socket     string
	checkpoint prestate.Checkpoint
	deadline   time.Time
	calls      int
	bytes      int
	rows       []any
}
type boundDiscovery struct {
	source *discoverySource
	world  string
	phase  func() string
}

func (s *discoverySource) bind(world string, phase func() string) prestate.Source {
	return &boundDiscovery{s, world, phase}
}
func (s *discoverySource) record(world, phase string, row prestate.ScenarioAccess) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if len(s.rows) >= 16384 {
		panic(&prestate.HostStop{Code: "DISCOVERY_ACCESS_LIMIT"})
	}
	s.rows = append(s.rows, struct {
		World  string                  `json:"world"`
		Phase  string                  `json:"phase"`
		Access prestate.ScenarioAccess `json:"access"`
	}{world, phase, row})
}
func (s *discoverySource) exchange(ctx context.Context, world, phase, kind string, a common.Address, keys []common.Hash, finish bool) (json.RawMessage, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.calls >= 128 || !time.Now().Before(s.deadline) {
		return nil, errors.New("DISCOVERY_BUDGET")
	}
	s.calls++
	request := map[string]any{"schema": DiscoveryProfile, "id": s.calls, "checkpoint": s.checkpoint, "world": world, "phase": phase, "kind": kind}
	if finish {
		request["completed"] = true
	} else {
		request["address"] = a
		if kind == "eth_getProof" {
			request["slots"] = append([]common.Hash{}, keys...)
		}
	}
	end := time.Now().Add(3 * time.Second)
	if s.deadline.Before(end) {
		end = s.deadline
	}
	if d, ok := ctx.Deadline(); ok && d.Before(end) {
		end = d
	}
	bounded, cancel := context.WithDeadline(ctx, end)
	defer cancel()
	connection, e := (&net.Dialer{}).DialContext(bounded, "unix", s.socket)
	if e != nil {
		return nil, e
	}
	defer connection.Close()
	if e = connection.SetDeadline(end); e != nil {
		return nil, e
	}
	raw, e := Canonical(request)
	if e != nil || len(raw) > 65536 {
		return nil, errors.New("DISCOVERY_REQUEST_LIMIT")
	}
	if _, e = connection.Write(append(raw, '\n')); e != nil {
		return nil, e
	}
	reader := bufio.NewReaderSize(connection, (2<<20)+1)
	raw, e = reader.ReadSlice('\n')
	if e != nil || len(raw) > 2<<20 {
		return nil, errors.New("DISCOVERY_RESPONSE_LIMIT")
	}
	s.bytes += len(raw)
	if s.bytes > 8<<20 {
		return nil, errors.New("DISCOVERY_BYTE_LIMIT")
	}
	var reply struct {
		ID     int             `json:"id"`
		Result json.RawMessage `json:"result"`
		Error  string          `json:"error"`
	}
	if e = decode(raw, &reply); e != nil {
		return nil, e
	}
	if reply.ID != s.calls || reply.Error != "" || len(reply.Result) == 0 {
		return nil, errors.New("DISCOVERY_BROKER_STOP: " + reply.Error)
	}
	return reply.Result, nil
}
func (s *boundDiscovery) GetProof(ctx context.Context, cp prestate.Checkpoint, a common.Address, keys []common.Hash) (*prestate.RPCProof, error) {
	if cp != s.source.checkpoint {
		return nil, errors.New("DISCOVERY_CHECKPOINT_DRIFT")
	}
	raw, e := s.source.exchange(ctx, s.world, s.phase(), "eth_getProof", a, keys, false)
	if e != nil {
		return nil, e
	}
	var proof prestate.RPCProof
	e = decode(raw, &proof)
	return &proof, e
}
func (s *boundDiscovery) GetCode(ctx context.Context, cp prestate.Checkpoint, a common.Address) ([]byte, error) {
	if cp != s.source.checkpoint {
		return nil, errors.New("DISCOVERY_CHECKPOINT_DRIFT")
	}
	raw, e := s.source.exchange(ctx, s.world, s.phase(), "eth_getCode", a, nil, false)
	if e != nil {
		return nil, e
	}
	var code hexutil.Bytes
	e = decode(raw, &code)
	return code, e
}
func (s *discoverySource) finish(ctx context.Context) error {
	_, e := s.exchange(ctx, "CONTROL", "DONE", "finish", common.Address{}, nil, true)
	return e
}
func discoveryFor(root string, binding map[string]any, cp prestate.Checkpoint) (*discoverySource, error) {
	socket, ok := binding["discoverySocket"].(string)
	if binding["discoveryProfile"] != DiscoveryProfile || !ok || socket != filepath.Join(filepath.Dir(root), "broker.sock") || len(socket) > 103 {
		return nil, errors.New("DISCOVERY_OPERATION_BINDING")
	}
	return &discoverySource{socket: socket, checkpoint: cp, deadline: time.Now().Add(30 * time.Second)}, nil
}
