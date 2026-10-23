"""Conservative macOS headroom policy, independent of the old scientific gate."""
import json
import time

from .common import REPO, require, store, portable, local_file

POLICY = json.loads((REPO/'sdk_alpha/policy.json').read_text())


def validate_sample(s):
    require(s['source'] == 'DARWIN_HOST_VM64/1' and s['platform'] == 'darwin-arm64', 'SENSOR_PROFILE')
    require(isinstance(s['boot'], str) and 0 < len(s['boot']) <= 128, 'BOOT_ENCODING')
    for key in ['beganNs', 'endedNs', 'physicalBytes', 'pageBytes', 'freePages',
                'speculativePages', 'pressureBefore', 'pressureAfter', 'swapOutPages',
                'swapUsedBeforeBytes', 'swapUsedBytes']:
        # Python consumes the native uint64 counters directly. Nanoseconds must
        # not acquire an artificial 104-day uptime ceiling from JS float limits.
        require(type(s[key]) is int and 0 <= s[key] <= (1<<64)-1, 'COUNTER_ENCODING_'+key)
    require(s['pageBytes'] in (4096, 16384) and s['physicalBytes'] > 0, 'PAGE_OR_PHYSICAL_ENCODING')
    require(s['freePages']*s['pageBytes'] <= s['physicalBytes']
            and s['speculativePages'] <= s['freePages'], 'IMPOSSIBLE_FREE_PAGES')
    require(0 < s['beganNs'] < s['endedNs']
            and (s['endedNs']-s['beganNs'])/1e9 <= POLICY['maximumSampleSeconds'], 'SENSOR_TIMING')
    require(s['pressureBefore'] == s['pressureAfter'] == POLICY['normalPressure'], 'MEMORY_PRESSURE')
    require(s['swapUsedBytes'] <= s['swapUsedBeforeBytes'], 'ACTIVE_SWAP_USAGE')
    return s


def assess(samples, runtime=False):
    require(len(samples) >= 2, 'TWO_RESOURCE_SAMPLES_REQUIRED')
    threshold = POLICY['minimumRuntimeFreeBytes' if runtime else 'minimumAdmissionFreeBytes']
    for s in samples:
        validate_sample(s)
        require(s['freePages']*s['pageBytes'] >= threshold, 'INSUFFICIENT_FREE_HEADROOM')
    for x, y in zip(samples, samples[1:]):
        require(all(x[k] == y[k] for k in ['boot', 'pageBytes', 'physicalBytes']), 'HOST_IDENTITY_CHANGED')
        gap = (y['beganNs']-x['endedNs'])/1e9
        require(0 < gap <= POLICY['maximumSampleGapSeconds'], 'RESOURCE_SAMPLE_GAP')
        if not runtime: require(gap >= 0.9, 'ADMISSION_SAMPLE_SPACING')
        require(y['swapOutPages'] == x['swapOutPages'], 'SWAP_OUTPUT_OR_COUNTER_REGRESSION')
        require(y['swapUsedBeforeBytes'] <= x['swapUsedBytes'], 'ACTIVE_SWAP_USAGE')
    return {'status': 'PASS', 'profile': POLICY['profile'], 'mode': 'runtime' if runtime else 'admission',
            'minimumObservedFreeBytes': min(s['freePages']*s['pageBytes'] for s in samples),
            'requiredFreeBytes': threshold, 'physicalBytes': samples[-1]['physicalBytes'],
            'reservedMemory': False, 'speculativeAlreadyIncludedInFree': True,
            'qualifiedScientificAdmission': False}


def capture_sensor(sensor, directory):
    # Existing bounded pipe capture preserves raw diagnostics before parsing.
    portable.guards.WS = REPO
    result, stdout, stderr = portable.guards.capture(
        [str(local_file(sensor))], directory, POLICY['sensorProcessWallSeconds'], 8192, 8192)
    require(not result['stop'] and result['ownedChildReaped'] and result['exitCode'] == 0
            and not stderr and len(stdout) < 8192, 'RESOURCE_SENSOR_FAILED: '+str(result))
    return validate_sample(json.loads(stdout))


def admission(sensor, directory):
    directory.mkdir()
    samples = []
    try:
        samples.append(capture_sensor(sensor, directory/'sample-0'))
        time.sleep(POLICY['admissionSpacingSeconds'])
        samples.append(capture_sensor(sensor, directory/'sample-1'))
        decision = assess(samples)
        return decision, samples
    finally:
        store(directory/'SAMPLES.json', samples)


class RuntimeGuard:
    def __init__(self, sensor, directory, previous):
        self.sensor, self.directory, self.previous = sensor, directory, previous
        self.last = 0.0
        self.count = 0
        directory.mkdir()

    def poll(self, force=False):
        if not force and time.monotonic()-self.last < POLICY['runtimeSampleSpacingSeconds']: return
        try:
            current = capture_sensor(self.sensor, self.directory/str(self.count))
            assess([self.previous, current], runtime=True)
            self.previous = current
            self.last = time.monotonic()
            self.count += 1
        except BaseException as error:
            store(self.directory/'STOP.json', {'cause': str(error), 'sample': self.count})
            raise
