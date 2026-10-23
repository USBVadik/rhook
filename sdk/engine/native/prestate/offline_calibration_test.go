package prestate

import (
	"errors"
	"testing"
)

func TestCalibrationFailureClassification(t *testing.T) {
	tests := []struct {
		err      error
		terminal string
	}{
		{nil, "CANONICAL_ACTUAL_ROOTS_MATCH"},
		{&HostStop{Code: "PROOF_SOURCE_UNAVAILABLE"}, "HOST_STOP_MISSING_STATE"},
		{&HostStop{Code: "TRIE_UPDATE_PREIMAGE_UNAVAILABLE"}, "HOST_STOP_MISSING_STATE"},
		{&HostStop{Code: "CANONICAL_ROOT_OR_GAS_MISMATCH"}, "CANONICAL_EXECUTION_MISMATCH"},
		{&HostStop{Code: "GENERATED_TRANSACTION_SEQUENCE_MISMATCH"}, "CANONICAL_EXECUTION_MISMATCH"},
		{&HostStop{Code: "CHECKPOINT_WINDOW_EXPIRED"}, "RUNTIME_OR_RESOURCE_STOP"},
		{errors.New("unexpected"), "RUNTIME_OR_RESOURCE_STOP"},
	}
	for _, tc := range tests {
		got, _ := ClassifyCalibrationError(tc.err)
		if got != tc.terminal {
			t.Fatalf("%v: %s != %s", tc.err, got, tc.terminal)
		}
	}
}
