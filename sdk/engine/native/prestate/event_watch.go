package prestate

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"io"
	"os"
	"os/exec"
	"strings"
	"sync"
	"syscall"
	"time"
)

type EventAuthority struct {
	OperationCommitment  string `json:"operationCommitment,omitempty"`
	Domain               string `json:"domain"`
	DecisionID           string `json:"decisionId"`
	Policy               string `json:"policyCommitment"`
	BinarySHA            string `json:"binarySha256"`
	AcquisitionID        string `json:"acquisitionDecisionId"`
	RuntimePath          string `json:"runtimePath"`
	FounderApproved      bool   `json:"founderApproved"`
	FreeConfirmed        bool   `json:"freeConfirmed"`
	PaidOveragesDisabled bool   `json:"paidOveragesDisabled"`
	WitnessBurstAllowed  bool   `json:"witnessBurst1000Allowed"`
	NotBefore            int64  `json:"notBeforeUnix"`
	Expires              int64  `json:"expiresUnix"`
	Actual               int    `json:"maximumActual"`
	Branch               int    `json:"maximumBranch"`
	B                    int    `json:"maximumB"`
}

func ValidateEventAuthorities(a EventAuthority, science *EventAuthority, p EventPolicy, binary string) error {
	now := time.Now().Unix()
	valid := func(x EventAuthority) bool {
		return x.FounderApproved && len(x.DecisionID) >= 8 && x.Policy == p.Commitment() && x.BinarySHA == binary && x.RuntimePath != "" && x.NotBefore <= now && x.Expires > now && x.Expires-now <= int64(p.Seconds) && (!isObservedPolicy(p) || (x.Expires > x.NotBefore && x.Expires-x.NotBefore <= int64(p.Seconds)))
	}
	if isObservedPolicy(p) && (len(a.OperationCommitment) != 64 || (science != nil && science.OperationCommitment != a.OperationCommitment)) {
		return errors.New("EXACT_OBSERVED_OPERATION_REQUIRED")
	}
	if !valid(a) || a.Domain != "MONITORING_ACQUISITION" || !a.FreeConfirmed || !a.PaidOveragesDisabled || !a.WitnessBurstAllowed || a.Actual != 0 || a.Branch != 0 || a.B != 0 {
		return errors.New("ACQUISITION_AUTHORITY_REQUIRED")
	}
	if science != nil {
		if !valid(*science) || science.Domain != "ONE_SHOT_HOOKR_EXECUTION" || science.RuntimePath != a.RuntimePath || science.DecisionID == a.DecisionID || science.AcquisitionID != a.DecisionID || science.Actual != 1 || science.Branch != 1 || science.B != 0 {
			return errors.New("SEPARATE_EXACT_SCIENTIFIC_AUTHORITY_REQUIRED")
		}
	}
	return nil
}
func EventResumeCheck(s EventState) error {
	if s.Draining {
		return errors.New("DRAINING_NO_RESUME")
	}
	if s.Stop != "" {
		return errors.New("PREVIOUS_STOP:" + s.Stop)
	}
	if s.Lock != nil || s.Consumed {
		return errors.New("LOCKED_OR_CONSUMED_NO_AUTOMATIC_NATIVE_RESUME")
	}
	if s.Began > 0 && s.Activation == 0 {
		return errors.New("ACTIVATION_UNCERTAIN")
	}
	for _, x := range s.Cases {
		if x.Status == "PENDING" {
			return errors.New("INTERRUPTED_CAPTURE_UNVERIFIED")
		}
	}
	return nil
}

type EventLiveConfig struct {
	Endpoint string
	HostGate []string
}
type EventRunSummary struct {
	Terminal               string
	SelectionAssurance     string `json:"selectionAssurance,omitempty"`
	Cause                  string `json:"cause,omitempty"`
	State                  EventState
	Pair                   *ProspectiveResult `json:"pair,omitempty"`
	EconomicAssurance      string
	HeterogeneousAgreement string
}

func RunEventWatcher(ctx context.Context, cfg EventLiveConfig, j *EventJournal, p EventPolicy, a EventAuthority, science *EventAuthority) (summary EventRunSummary) {
	return runEventWatcherWith(ctx, cfg, j, p, a, science, NewEventRPC, subscribeEventWS)
}
func runEventWatcherWith(ctx context.Context, cfg EventLiveConfig, j *EventJournal, p EventPolicy, a EventAuthority, science *EventAuthority, newRPC func(string, *EventJournal, EventPolicy, string, string, WriteEvidence) (*RPCSource, error), subscribe func(context.Context, string, EventMeter, WriteEvidence) (eventSocket, string, error)) (summary EventRunSummary) {
	if isObservedPolicy(p) {
		summary.SelectionAssurance = observedAssurance
	}
	summary.EconomicAssurance = "UNRESOLVED"
	summary.HeterogeneousAgreement = "NOT_EVALUATED"
	summary.Terminal = "ACQUISITION_STOP"
	var controller *EventController
	hardCancel := func() {}
	fail := func(e error) {
		summary.Cause = e.Error()
		if p.Coverage != nil && controller != nil && !j.Snapshot().Consumed && j.Snapshot().Stop == "" {
			if err := controller.BeginDrain(e.Error()); err != nil {
				summary.Cause = "DRAIN_JOURNAL_UNCERTAIN"
				hardCancel()
			}
			return
		}
		j.Halt(e.Error())
	}
	defer func() { summary.State = j.Snapshot() }()
	if e := j.CheckMarkers(); e != nil {
		fail(e)
		return
	}
	if e := EventResumeCheck(j.Snapshot()); e != nil {
		fail(e)
		return
	}
	ab, _ := json.Marshal(a)
	sb, _ := json.Marshal(science)
	as, ss := ByteDigest(ab), ByteDigest(sb)
	prior := j.Snapshot()
	if p.Coverage != nil && prior.Began != 0 {
		if isObservedPolicy(p) {
			fail(errors.New("OBSERVED_PROCESS_RESTART_NOT_AUTHORIZED"))
		} else {
			fail(errors.New("QUIET_PROCESS_RESTART_NOT_AUTHORIZED"))
		}
		return
	}
	if prior.Began != 0 && (prior.AcquisitionAuthoritySHA != as || prior.ScienceAuthoritySHA != ss) {
		fail(errors.New("AUTHORITY_BINDINGS_CHANGED_ON_RESTART"))
		return
	}
	if j.Snapshot().Began == 0 {
		if e := j.Update("BEGIN_ACQUISITION", func(s *EventState) error {
			s.Began = time.Now().UnixNano()
			s.AcquisitionAuthoritySHA = as
			s.ScienceAuthoritySHA = ss
			s.Expires = time.Unix(a.Expires, 0).UnixNano()
			return nil
		}); e != nil {
			summary.Cause = e.Error()
			return
		}
	}
	ctx, cancel := context.WithDeadline(ctx, time.Unix(0, j.Snapshot().Expires))
	defer cancel()
	hardCancel = cancel
	if p.Coverage != nil {
		j.SetHardCancel(cancel)
	}
	rootWrite := EventWriter(j, p, "records")
	if e := j.Update("CONNECTION_GENERATION", func(s *EventState) error {
		s.Reconnects++
		if s.Reconnects > p.Reconnects+1 {
			return errors.New("RECONNECT_BUDGET")
		}
		return nil
	}); e != nil {
		fail(e)
		return
	}
	monitor, e := newRPC(cfg.Endpoint, j, p, "monitor", fmt.Sprintf("MONITOR_%d", j.Snapshot().Reconnects), rootWrite)
	if e != nil {
		fail(e)
		return
	}
	var chain string
	if e = monitor.call(ctx, "eth_chainId", []any{}, &chain); e != nil || chain != "0x1237" {
		fail(errors.New("CHAIN_CHECK_FAILED"))
		return
	}
	if j.Snapshot().Activation == 0 {
		_, anchor, e := eventHeader(ctx, monitor, "latest")
		if e != nil {
			fail(e)
			return
		}
		if anchor.Number.Uint64() <= 92076104 {
			fail(errors.New("ACTIVATION_BOUNDARY"))
			return
		}
		if e = j.Update("ACTIVATION", func(s *EventState) error {
			s.Activation = anchor.Number.Uint64()
			s.Cursor = s.Activation
			s.ActivationHash = anchor.Hash()
			s.CursorHash = anchor.Hash()
			return nil
		}); e != nil {
			fail(e)
			return
		}
	}
	controller = NewEventController(j, p, func(captureCtx context.Context, l *types.Log, write WriteEvidence) (*EventCapture, error) {
		captureCtx, stop := context.WithTimeout(captureCtx, time.Duration(p.CaptureSeconds)*time.Second)
		defer stop()
		rpc, e := newRPC(cfg.Endpoint, j, p, l.BlockHash.Hex(), "CAPTURE_RPC", write)
		if e != nil {
			return nil, e
		}
		began := time.Now()
		out, e := CaptureEventPackage(captureCtx, rpc, l, write)
		if save := EmitJSON(write, "CAPTURE_TIMING.json", map[string]any{"beganUTC": began.UTC(), "elapsedSeconds": time.Since(began).Seconds(), "captureRPC": j.Snapshot().Cases[l.BlockHash.Hex()].RPC, "nativeInvocations": 0}); save != nil && e == nil {
			e = save
		}
		return out, e
	})
	defer func() {
		if p.Coverage != nil && j.Snapshot().Draining && j.Snapshot().Stop == "" {
			controller.Wait()
			j.Halt(j.Snapshot().DrainReason)
			cancel()
		} else {
			cancel()
			controller.Wait()
		}
	}()
	var coverage *RPCSource
	var tick <-chan time.Time
	if p.Coverage != nil && !isObservedPolicy(p) {
		if !p.Coverage.Valid() {
			fail(errors.New("INVALID_QUIET_POLICY"))
			return
		}
		coverage, e = newRPC(p.Coverage.Endpoint, j, p, "coverage", "COVERAGE", rootWrite)
		if e != nil {
			fail(e)
			return
		}
		var chain string
		if e = coverage.call(ctx, "eth_chainId", []any{}, &chain); e != nil || chain != "0x1237" {
			fail(errors.New("COVERAGE_CHAIN_CHECK"))
			return
		}
		timer := time.NewTicker(time.Duration(p.Coverage.PollSeconds) * time.Second)
		defer timer.Stop()
		tick = timer.C
	}
	reconcile := func(to uint64) error {
		if isObservedPolicy(p) {
			return controller.CompleteObserved(ctx, func(fetchCtx context.Context, hash common.Hash, write WriteEvidence) ([]*types.Log, error) {
				rpc, err := newRPC(cfg.Endpoint, j, p, hash.Hex(), "OBSERVED_LOGS_RPC", write)
				if err != nil {
					return nil, err
				}
				var logs []*types.Log
				err = rpc.call(fetchCtx, "eth_getLogs", []any{map[string]any{"blockHash": hash, "address": []common.Address{hookrManager, hookrRouter}, "topics": []any{[]common.Hash{swapTopic, routerTopic}, hookrPoolID}}}, &logs)
				return logs, err
			})
		}
		if coverage == nil {
			return ReconcileEventRange(ctx, monitor, controller, to)
		}
		fetch, stop := context.WithTimeout(ctx, time.Duration(p.Coverage.CycleSeconds)*time.Second)
		defer stop()
		return reconcileQuietRange(ctx, fetch, coverage, controller, to)
	}
	events := make(chan uint64, 64)
	disconnected := make(chan error, 1)
	var reader sync.WaitGroup
	for {
		m := EventMeter{j, p, "monitor"}
		conn, subscription, e := subscribe(ctx, cfg.Endpoint, m, rootWrite)
		if e != nil {
			fail(e)
			return
		}
		if e = j.Update("SUBSCRIBED", func(s *EventState) error {
			s.Connected = true
			if isObservedPolicy(p) {
				if s.Observed != nil {
					return errors.New("OBSERVED_SUBSCRIPTION_CANNOT_RESTART")
				}
				s.Observed = &ObservedDeliveryState{Started: time.Now().UnixNano(), Logs: map[string]string{}}
			}
			return nil
		}); e != nil {
			conn.Close()
			fail(e)
			return
		}
		reader.Add(1)
		go func() {
			defer reader.Done()
			secret := ""
			if n := strings.LastIndex(cfg.Endpoint, "/"); n >= 0 {
				secret = cfg.Endpoint[n+1:]
			}
			for {
				frame, e := eventReadWS(conn, m, rootWrite, secret)
				if e == nil && (frame.Method != "eth_subscription" || frame.Params.Subscription != subscription || frame.Params.Result == nil) {
					e = errors.New("WSS_NOTIFICATION_IDENTITY")
				}
				if e == nil {
					e = controller.Observe(ctx, frame.Params.Result)
				}
				if e != nil {
					j.Update("DISCONNECTED", func(s *EventState) error { s.Connected = false; return nil })
					if e.Error() != "WSS_DISCONNECTED" && ctx.Err() == nil && !j.Snapshot().Draining {
						j.Halt(e.Error())
					}
					select {
					case disconnected <- e:
					default:
					}
					return
				}
				select {
				case events <- frame.Params.Result.BlockNumber:
				default:
					j.Halt("WSS_EVENT_QUEUE_OVERFLOW")
					select {
					case disconnected <- errors.New("WSS_EVENT_QUEUE_OVERFLOW"):
					default:
					}
					return
				}
			}
		}()
		// Subscription is already receiving and triggering capture. This H1 closes
		// the H0->subscribe startup interval; no periodic head/body polling follows.
		if !isObservedPolicy(p) {
			_, head, x := eventHeader(ctx, monitor, "latest")
			e = x
			if e == nil {
				e = reconcile(head.Number.Uint64())
			}
		}
		reconnect := false
		for e == nil {
			if x := eventAdmissionReady(ctx, j); x != nil {
				e = x
				break
			}
			state := j.Snapshot()
			if state.Stop != "" || state.Draining {
				e = errors.New("ACQUISITION_TERMINAL_OR_DRAINING")
				if state.Stop != "" {
					e = errors.New(state.Stop)
				}
				break
			}
			if state.Lock != nil {
				if isObservedPolicy(p) {
					if e = validateObservedLock(state); e != nil {
						break
					}
					if e = j.CheckMarkers(); e != nil {
						break
					}
				}
				if science == nil {
					summary.Terminal = "FIRST_ELIGIBLE_CAPTURED_NATIVE_DISABLED"
					conn.Close()
					reader.Wait()
					return
				}
				if time.Now().Unix() >= science.Expires {
					e = errors.New("SCIENTIFIC_AUTHORITY_EXPIRED")
					break
				}
				if len(cfg.HostGate) == 0 {
					e = errors.New("PINNED_HOST_GATE_REQUIRED")
					break
				}
				if e = j.Marker("SCIENTIFIC_CONSUMED.json", map[string]any{"scienceAuthoritySHA": state.ScienceAuthoritySHA, "acquisitionAuthoritySHA": state.AcquisitionAuthoritySHA, "lock": state.Lock, "retryAllowed": false}); e != nil {
					break
				}
				e = j.Update("SCIENTIFIC_AUTHORITY_CONSUMED", func(s *EventState) error {
					if s.Consumed || s.Lock == nil || !s.Connected || s.Stop != "" || s.Draining {
						return errors.New("AUTHORITY_USED_OR_DISCONNECTED")
					}
					s.Consumed = true
					return nil
				})
				if e != nil {
					break
				}
				cap, x := controller.load(ctx, state.Lock.Selection.BlockHash)
				if x != nil {
					e = x
					break
				}
				if cap.Inventory == nil || ByteDigest(cap.Package) != state.Lock.PackageSHA || cap.Inventory.Checkpoint != state.Lock.Checkpoint {
					e = errors.New("LOCKED_PACKAGE_BINDING_MISMATCH")
					break
				}
				if eventAdmissionReady(ctx, j) != nil || j.Snapshot().Stop != "" || j.Snapshot().Draining {
					e = errors.New("STOP_BEFORE_HOST")
					break
				}
				if x = runEventHostGate(ctx, cfg.HostGate, rootWrite); x != nil {
					e = x
					break
				}
				// Revalidate selected hash immediately before native entry; use the same
				// case budget as capture and both worlds' original-root hydration.
				rpc, x := newRPC(cfg.Endpoint, j, p, state.Lock.Selection.BlockHash.Hex(), "NATIVE_RPC", EventWriter(j, p, eventCaptureDir(state.Lock.Selection.BlockHash)))
				if x != nil {
					e = x
					break
				}
				_, again, x := eventHeader(ctx, rpc, fmt.Sprintf("0x%x", state.Lock.Selection.BlockNumber))
				if x != nil || again.Hash() != state.Lock.Selection.BlockHash {
					e = errors.New("LOCKED_REORG_BEFORE_NATIVE")
					break
				}
				if eventAdmissionReady(ctx, j) != nil || j.Snapshot().Stop != "" || j.Snapshot().Draining || !j.Snapshot().Connected {
					e = errors.New("CONTINUITY_LOST_BEFORE_NATIVE")
					break
				}
				pairCtx, stop := context.WithDeadline(ctx, minTime(time.Now().Add(time.Duration(p.NativeSeconds)*time.Second), time.Unix(science.Expires, 0)))
				nativeWrite := EventWriter(j, p, "native")
				emit := func(name string, v any) error {
					if eventAdmissionReady(pairCtx, j) != nil || j.Snapshot().Stop != "" || j.Snapshot().Draining || !j.Snapshot().Connected {
						return errors.New("CONTINUITY_LOST_BEFORE_NATIVE_PHASE")
					}
					return EmitJSON(nativeWrite, name+".json", v)
				}
				summary.Pair = runEventPairGuarded(pairCtx, j, p, func() *ProspectiveResult {
					return RunPreparedEventPair(pairCtx, rpc, nativeWrite, emit, cap, state.Lock.Selection.Subject)
				})
				if why := j.Snapshot().Stop; why != "" {
					summary.Pair.Terminal = "RUNTIME_OR_RESOURCE_STOP"
					summary.Pair.Cause = why
				}
				if !j.Snapshot().Connected {
					summary.Pair.Terminal = "RUNTIME_OR_RESOURCE_STOP"
					summary.Pair.Cause = "CONTINUITY_LOST_DURING_NATIVE"
				}
				stop()
				summary.Terminal = summary.Pair.Terminal
				conn.Close()
				reader.Wait()
				j.Halt(summary.Terminal)
				return
			}
			select {
			case <-tick:
				e = QuietCoverageStep(ctx, coverage, controller)
			case n := <-events:
				e = reconcile(n)
			case err := <-disconnected:
				e = err
				reconnect = true
			case <-ctx.Done():
				e = ctx.Err()
			}
		}
		if e != nil && p.Coverage != nil && !reconnect && j.Snapshot().Stop == "" && !j.Snapshot().Consumed {
			if drainErr := controller.BeginDrain(e.Error()); drainErr != nil {
				cancel()
				e = errors.New("DRAIN_JOURNAL_UNCERTAIN")
			}
		}
		conn.Close()
		reader.Wait()
		if reconnect && isObservedPolicy(p) {
			fail(errors.New("OBSERVED_WSS_DISCONNECTED_NO_RECONNECT"))
			return
		}
		if reconnect && ctx.Err() == nil && j.Snapshot().Lock == nil && j.Snapshot().Stop == "" {
			if e = j.Update("RECONNECT", func(s *EventState) error {
				s.Reconnects++
				if s.Reconnects > p.Reconnects+1 {
					return errors.New("RECONNECT_BUDGET")
				}
				return nil
			}); e != nil {
				fail(e)
				return
			}
			continue
		}
		if ctx.Err() != nil && j.Snapshot().Lock == nil {
			if j.FatalReason() != "" && j.Snapshot().Stop == "" {
				summary.Terminal = "INTERRUPTED_UNVERIFIED"
				summary.Cause = j.FatalReason()
				return
			}
			if j.Snapshot().Stop != "" || (e != nil && e.Error() == "DRAIN_JOURNAL_UNCERTAIN") {
				summary.Terminal = "ACQUISITION_STOP"
				if e != nil {
					summary.Cause = e.Error()
				}
				if j.Snapshot().Stop != "" {
					summary.Cause = j.Snapshot().Stop
				}
				return
			}
			summary.Terminal = "ACQUISITION_WINDOW_ENDED_NO_LOCK"
			j.Halt(summary.Terminal)
			return
		}
		if e != nil {
			fail(e)
		}
		return
	}
}
func eventAdmissionReady(ctx context.Context, j *EventJournal) error {
	if e := ctx.Err(); e != nil {
		return e
	}
	if reason := j.FatalReason(); reason != "" {
		return errors.New("JOURNAL_FATAL:" + reason)
	}
	return nil
}
func runEventHostGate(ctx context.Context, command []string, write WriteEvidence) error {
	child, stop := context.WithTimeout(ctx, 8*time.Second)
	defer stop()
	cmd := exec.CommandContext(child, command[0], command[1:]...)
	cmd.Env = []string{"PATH=/usr/bin:/bin:/usr/sbin:/sbin", "LANG=C", "TZ=UTC"}
	var out strings.Builder
	bounded := &eventLimitedWriter{Writer: &out, Remaining: 65536}
	cmd.Stdout = bounded
	cmd.Stderr = bounded
	e := cmd.Run()
	raw := []byte(out.String())
	if x := write("HOST_GATE.json", raw); x != nil {
		return x
	}
	if e != nil {
		return errors.New("LEGACY_HOST_ADMISSION_STOP")
	}
	return nil
}

type eventLimitedWriter struct {
	io.Writer
	Remaining int
}

func (w *eventLimitedWriter) Write(b []byte) (int, error) {
	if len(b) > w.Remaining {
		return 0, errors.New("OUTPUT_LIMIT")
	}
	n, e := w.Writer.Write(b)
	w.Remaining -= n
	return n, e
}
func runEventPairGuarded(ctx context.Context, j *EventJournal, p EventPolicy, run func() *ProspectiveResult) *ProspectiveResult {
	var start syscall.Rusage
	syscall.Getrusage(syscall.RUSAGE_SELF, &start)
	base := float64(start.Utime.Sec+start.Stime.Sec) + float64(start.Utime.Usec+start.Stime.Usec)/1e6
	done := make(chan struct{})
	defer close(done)
	go func() {
		ticker := time.NewTicker(200 * time.Millisecond)
		defer ticker.Stop()
		for {
			select {
			case <-done:
				return
			case <-ctx.Done():
				select {
				case <-done:
					return
				default:
				}
				fmt.Fprintln(os.Stderr, "NATIVE_WALL_OR_OPERATION_STOP")
				os.Exit(124)
			case <-ticker.C:
				select {
				case <-done:
					return
				default:
				}
				var r syscall.Rusage
				e := syscall.Getrusage(syscall.RUSAGE_SELF, &r)
				cpu := float64(r.Utime.Sec+r.Stime.Sec) + float64(r.Utime.Usec+r.Stime.Usec)/1e6 - base
				if e != nil || r.Maxrss <= 0 || r.Maxrss > 4<<30 || cpu > float64(p.NativeCPU) {
					fmt.Fprintln(os.Stderr, "NATIVE_RESOURCE_STOP")
					os.Exit(125)
				}
			}
		}
	}()
	out := run()
	var r syscall.Rusage
	err := syscall.Getrusage(syscall.RUSAGE_SELF, &r)
	cpu := float64(r.Utime.Sec+r.Stime.Sec) + float64(r.Utime.Usec+r.Stime.Usec)/1e6 - base
	if err != nil || r.Maxrss <= 0 || r.Maxrss > 4<<30 || cpu > float64(p.NativeCPU) {
		out.Terminal = "RUNTIME_OR_RESOURCE_STOP"
		out.Cause = "NATIVE_FINAL_RESOURCE_LIMIT"
	}
	return out
}
