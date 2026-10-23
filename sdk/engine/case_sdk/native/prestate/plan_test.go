package prestate

import (
	"github.com/ethereum/go-ethereum/common"
	"testing"
)

func oldCaseWord() common.Hash {
	return common.HexToHash("0x0000000007d0000000000064000000020000000000000000002cec0000000000")
}
func TestCaseLPReplacementAllValues(t *testing.T) {
	for n := 0; n < 100; n++ {
		old := oldCaseWord()
		next := old
		next[10] = 0
		next[11] = byte(n)
		got, e := CheckedCaseLPReplacement(old, old, next)
		if e != nil || got != next {
			t.Fatalf("value %d: %v", n, e)
		}
	}
}
func TestCaseLPChecksFullOldWord(t *testing.T) {
	old := oldCaseWord()
	next := old
	next[11] = 50
	current := old
	current[0] ^= 1
	if _, e := CheckedCaseLPReplacement(current, old, next); e == nil {
		t.Fatal("changed full original word accepted")
	}
}
func TestCaseLPRejectsIdentityAndBits(t *testing.T) {
	old := oldCaseWord()
	next := old
	next[11] = 50
	i := LPIntervention{Pool: hookrPoolID, Account: hookrRules, Slot: hookrConfigSlot, Mask: hookrLPMask, ExpectedOldWord: old, NewWord: next}
	if e := ValidateCaseLPIntervention(i, Checkpoint{}); e != nil {
		t.Fatal(e)
	}
	bad := i
	bad.Slot[0] ^= 1
	if ValidateCaseLPIntervention(bad, Checkpoint{}) == nil {
		t.Fatal("changed slot")
	}
	bad = i
	bad.NewWord[0] ^= 1
	if ValidateCaseLPIntervention(bad, Checkpoint{}) == nil {
		t.Fatal("changed unrelated bits")
	}
	for _, n := range []byte{100, 101, 255} {
		bad = i
		bad.NewWord[11] = n
		if ValidateCaseLPIntervention(bad, Checkpoint{}) == nil {
			t.Fatal("invalid range")
		}
	}
}
func TestCaseLPLeavesLegacyZeroGuardUnchanged(t *testing.T) {
	old := oldCaseWord()
	got, e := CheckedLPReplacement(old, old)
	if e != nil || got[11] != 0 {
		t.Fatal("legacy zero guard changed")
	}
	i := LPIntervention{Pool: hookrPoolID, Account: hookrRules, Slot: hookrConfigSlot, Mask: hookrLPMask, ExpectedOldWord: old, NewWord: old}
	i.NewWord[11] = 50
	if ValidateLPIntervention(i, Checkpoint{}) == nil {
		t.Fatal("legacy accepted fifty")
	}
}
