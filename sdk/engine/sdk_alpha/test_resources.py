import copy
import unittest

from sdk_alpha.resources import POLICY, assess, validate_sample


def sample(t=1, gib=16, free=6, outs=100, used=0):
    return dict(source='DARWIN_HOST_VM64/1', platform='darwin-arm64', boot='test-boot',
                beganNs=t*10**9, endedNs=t*10**9+1000, physicalBytes=gib<<30,
                pageBytes=16384, freePages=free*(1<<30)//16384, speculativePages=100,
                pressureBefore=1, pressureAfter=1, swapOutPages=outs,
                swapUsedBeforeBytes=used, swapUsedBytes=used)


class ResourcePolicyTests(unittest.TestCase):
    def test_not_tied_to_total_ram(self):
        for gib in [8, 16, 24, 32, 64]:
            with self.subTest(gib=gib):
                self.assertEqual(assess([sample(1, gib), sample(2, gib)])['status'], 'PASS')

    def test_large_total_does_not_override_insufficient_headroom(self):
        with self.assertRaisesRegex(ValueError, 'FREE_HEADROOM'):
            assess([sample(1, 64, 5), sample(2, 64, 5)])

    def test_speculative_is_not_added_to_free_again(self):
        x = sample(free=5); x['speculativePages'] = 1<<16
        with self.assertRaisesRegex(ValueError, 'FREE_HEADROOM'):
            assess([x, dict(x, beganNs=2*10**9, endedNs=2*10**9+1000)])

    def test_pressure_at_either_boundary_stops(self):
        for key in ['pressureBefore', 'pressureAfter']:
            for pressure in [2, 4, 0, True]:
                y = sample(2); y[key] = pressure
                with self.assertRaises(ValueError): assess([sample(), y])

    def test_swap_growth_and_regression_stop(self):
        for changes in [dict(swapOutPages=101), dict(swapOutPages=99),
                        dict(swapUsedBytes=1), dict(swapUsedBeforeBytes=1, swapUsedBytes=1)]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                assess([sample(), dict(sample(2), **changes)])

    def test_boot_or_page_or_physical_changes_stop(self):
        for changes in [dict(boot='other'), dict(pageBytes=4096), dict(physicalBytes=32<<30)]:
            with self.assertRaises(ValueError): assess([sample(), dict(sample(2), **changes)])

    def test_runtime_uses_reserve_but_keeps_pressure_and_swap_guards(self):
        self.assertEqual(assess([sample(), sample(2, free=2)], runtime=True)['status'], 'PASS')
        with self.assertRaisesRegex(ValueError, 'FREE_HEADROOM'):
            assess([sample(), sample(2, free=1)], runtime=True)

    def test_malformed_oversized_or_non_integer_counter_rejected(self):
        for key, value in [('freePages', -1), ('freePages', True), ('freePages', 1<<60),
                           ('pageBytes', 0), ('boot', ''), ('source', 'old')]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_sample(dict(sample(), **{key: value}))

    def test_stale_overlapping_or_slow_samples_rejected(self):
        for y in [sample(0), sample(1), sample(5), dict(sample(2), endedNs=3*10**9)]:
            with self.assertRaises(ValueError): assess([sample(), y])

    def test_policy_cannot_claim_reservation(self):
        self.assertFalse(POLICY['reservedMemory'])
        self.assertEqual(POLICY['workerRssBytes'], 4<<30)
        self.assertEqual(POLICY['minimumAdmissionFreeBytes'], (5<<30)+(256<<20))
        self.assertEqual(POLICY['sensorProcessWallSeconds'], 1)
        self.assertEqual(POLICY['maximumSampleSeconds'], .25)

    def test_valid_long_uptime_does_not_acquire_js_float_ceiling(self):
        self.assertEqual(assess([sample(120*86400), sample(120*86400+1)])['status'], 'PASS')


if __name__ == '__main__': unittest.main()
