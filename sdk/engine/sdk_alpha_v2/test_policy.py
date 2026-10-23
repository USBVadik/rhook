"""Pure synthetic samples only; this suite never invokes the real host sensor."""
import copy
import unittest

from sdk_alpha.resources import assess as assess_v1
from sdk_alpha_v2.resources import POLICY, assess, validate_sample


def sample(t=1, free_bytes=2<<30, physical=16<<30):
    page=16384
    return dict(source='DARWIN_HOST_VM64/1',platform='darwin-arm64',boot='synthetic-boot',
                beganNs=t*10**9,endedNs=t*10**9+1000,physicalBytes=physical,pageBytes=page,
                freePages=free_bytes//page,speculativePages=100,pressureBefore=1,pressureAfter=1,
                swapOutPages=100,swapUsedBeforeBytes=1<<30,swapUsedBytes=1<<30)


class V2PolicyTests(unittest.TestCase):
    def test_class_and_margin_are_explicit_and_algebraically_consistent(self):
        self.assertEqual(POLICY['profile'],'developer-darwin-arm64/2')
        self.assertEqual(POLICY['workerRssBytes'],1<<30)
        self.assertEqual(POLICY['osReserveBytes'],256<<20)
        self.assertEqual(POLICY['supervisorAllowanceBytes'],256<<20)
        self.assertEqual(POLICY['minimumAdmissionFreeBytes'],(1<<30)+(512<<20))
        self.assertEqual(POLICY['minimumRuntimeFreeBytes'],512<<20)
        self.assertFalse(POLICY['reservedMemory'])

    def test_admission_boundary_one_page_below_at_and_above(self):
        threshold=POLICY['minimumAdmissionFreeBytes']
        for delta,passing in [(-16384,False),(0,True),(16384,True)]:
            with self.subTest(delta=delta):
                rows=[sample(1,threshold+delta),sample(2,threshold+delta)]
                if passing:self.assertEqual(assess(rows)['status'],'PASS')
                else:
                    with self.assertRaisesRegex(ValueError,'FREE_HEADROOM'):assess(rows)

    def test_runtime_boundary_is_margin_not_admission_budget(self):
        threshold=POLICY['minimumRuntimeFreeBytes']
        for delta in [-16384,0,16384]:
            rows=[sample(1,threshold+delta),sample(2,threshold+delta)]
            if delta>=0:self.assertEqual(assess(rows,runtime=True)['status'],'PASS')
            else:
                with self.assertRaisesRegex(ValueError,'FREE_HEADROOM'):assess(rows,runtime=True)

    def test_total_ram_is_not_an_admission_selector(self):
        for gib in [4,8,16,24,32,64]:
            with self.subTest(gib=gib):
                self.assertEqual(assess([sample(1,physical=gib<<30),sample(2,physical=gib<<30)])['status'],'PASS')

    def test_normal_and_abnormal_pressure(self):
        for key in ['pressureBefore','pressureAfter']:
            for value in [0,2,4,True]:
                y=sample(2);y[key]=value
                with self.assertRaises(ValueError):assess([sample(),y])

    def test_stable_swap_is_allowed_but_growth_and_regression_are_not(self):
        self.assertEqual(assess([sample(),sample(2)])['status'],'PASS')
        for change in [dict(swapOutPages=101),dict(swapOutPages=99),
                       dict(swapUsedBytes=(1<<30)+1),dict(swapUsedBeforeBytes=(1<<30)+1)]:
            with self.subTest(change=change),self.assertRaises(ValueError):
                assess([sample(),dict(sample(2),**change)])

    def test_missing_and_inconsistent_samples_fail_closed(self):
        for key in sample():
            bad=sample(2);bad.pop(key)
            with self.subTest(key=key),self.assertRaises((ValueError,KeyError)):
                assess([sample(),bad])
        for change in [dict(boot='other'),dict(physicalBytes=32<<30),dict(pageBytes=4096),
                       dict(freePages=-1),dict(freePages=True),dict(beganNs=0),dict(endedNs=4*10**9)]:
            with self.assertRaises(ValueError):assess([sample(),dict(sample(2),**change)])
        for rows in [[],[sample()], [sample(),sample(1)], [sample(),sample(5)]]:
            with self.assertRaises(ValueError):assess(rows)

    def test_speculative_pages_cannot_be_double_counted(self):
        below=POLICY['minimumAdmissionFreeBytes']-16384
        x=sample(1,below);x['speculativePages']=10000
        y=dict(x,beganNs=2*10**9,endedNs=2*10**9+1000)
        with self.assertRaisesRegex(ValueError,'FREE_HEADROOM'):assess([x,y])

    def test_v1_and_v2_reassessment_are_independent(self):
        rows=[sample(),sample(2)];before=copy.deepcopy(rows)
        with self.assertRaisesRegex(ValueError,'FREE_HEADROOM'):assess_v1(rows)
        self.assertEqual(assess(rows)['status'],'PASS')
        with self.assertRaisesRegex(ValueError,'FREE_HEADROOM'):assess_v1(rows)
        self.assertEqual(rows,before)


if __name__=='__main__':unittest.main()
