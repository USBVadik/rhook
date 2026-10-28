package scenario

import "context"

// The OS supervisor remains responsible for preemption and physical-host guards.
// Enter prevents a third producer invocation even if the controller regresses.
type NativeGate interface {
	Enter(context.Context, string) error
}
