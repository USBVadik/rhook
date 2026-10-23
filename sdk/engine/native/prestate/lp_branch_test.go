package prestate

import (
	"github.com/ethereum/go-ethereum/common"
	"testing"
)

func testLPRequest() LPIntervention {
	old := syntheticLPWord()
	changed, _ := CheckedLPReplacement(old, old)
	return LPIntervention{Checkpoint{4663, 123, common.HexToHash("0x01"), common.HexToHash("0x02")}, hookrPoolID, hookrRules, hookrConfigSlot, hookrLPMask, old, changed}
}

func TestExactLPWordPreservesEveryUnrelatedBit(t *testing.T) {
	i := testLPRequest()
	if e := ValidateLPIntervention(i, i.Checkpoint); e != nil {
		t.Fatal(e)
	}
	for n := 0; n < 32; n++ {
		if n == 10 || n == 11 {
			if i.NewWord[n] != 0 {
				t.Fatal("lp not zero")
			}
		} else if i.NewWord[n] != i.ExpectedOldWord[n] {
			t.Fatal("extra bit changed")
		}
	}
	wrong := i.ExpectedOldWord
	wrong[31] ^= 1
	if _, e := CheckedLPReplacement(wrong, i.ExpectedOldWord); e == nil {
		t.Fatal("accepted partial matching word")
	}
	for _, v := range []byte{0, 1, 27, 99, 101, 255} {
		wrong = i.ExpectedOldWord
		wrong[11] = v
		if _, e := CheckedLPReplacement(wrong, wrong); e == nil {
			t.Fatal("wrong lp accepted")
		}
	}
}

func TestLPIdentityRejectsAnyOtherInitialMutation(t *testing.T) {
	changes := []func(*LPIntervention){
		func(x *LPIntervention) { x.Checkpoint.StateRoot[0] ^= 1 },
		func(x *LPIntervention) { x.Account[0] ^= 1 }, func(x *LPIntervention) { x.Pool[0] ^= 1 },
		func(x *LPIntervention) { x.Slot[31] ^= 1 }, func(x *LPIntervention) { x.Mask[0] ^= 1 },
		func(x *LPIntervention) { x.NewWord[31] ^= 1 },
	}
	for n, change := range changes {
		i := testLPRequest()
		cp := i.Checkpoint
		change(&i)
		if ValidateLPIntervention(i, cp) == nil {
			t.Fatalf("accepted mutation %d", n)
		}
	}
}

func TestUnknownLPAccountNeverBecomesZeroWord(t *testing.T) {
	f := makeFixture(t)
	b := fixtureBridge(t, f)
	i := testLPRequest()
	i.Checkpoint = f.checkpoint
	if e := b.LoadWitness(f.checkpoint, nil, nil); e != nil {
		t.Fatal(e)
	}
	var err error
	err = b.Protect(func() error { _, e := applyLPOverlay(b, i, hookrRulesCodeHash); return e })
	if !IsHostStop(err) || b.lpPatched {
		t.Fatalf("unknown account accepted: %v", err)
	}
}

func syntheticLPWord() common.Hash {
	var w common.Hash
	for n := range w {
		w[n] = byte(n*7 + 1)
	}
	w[10], w[11] = 0, 100
	return w
}
