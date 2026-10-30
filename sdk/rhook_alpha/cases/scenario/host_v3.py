"""Versioned availability telemetry; pressure/resource/identity guards stay active."""
from pathlib import Path
import time
from developer.files import load, require, save, sha, strict

HERE = Path(__file__).resolve().parent
POLICY = load(HERE / 'host_v3_policy.json', 65536)
PROFILE = POLICY['profile']
POLICY_SHA = sha(HERE / 'host_v3_policy.json')
COUNTERS = ('beganNs', 'endedNs', 'physicalBytes', 'pageBytes', 'freePages',
            'speculativePages', 'inactivePages', 'activePages', 'fileBackedPages',
            'anonymousPages', 'purgeablePages', 'wiredPages', 'compressorPages',
            'compressedLogicalPages', 'compressions', 'decompressions',
            'pressureBefore', 'pressureAfter', 'swapInPages', 'swapOutPages',
            'swapUsedBeforeBytes', 'swapUsedBytes')


def validate_sample(sample):
    require(type(sample) is dict and all(k in sample for k in (*COUNTERS, 'source', 'platform', 'boot')), 'V3_SENSOR_FIELDS')
    require(sample['source'] == 'DARWIN_HOST_VM64/3' and sample['platform'] == 'darwin-arm64', 'V3_SENSOR_PROFILE')
    require(type(sample['boot']) is str and 0 < len(sample['boot']) <= 128, 'BOOT_ENCODING')
    for key in COUNTERS:
        require(type(sample[key]) is int and 0 <= sample[key] < 1 << 64, 'COUNTER_ENCODING_' + key)
    require(sample['pageBytes'] in (4096, 16384) and sample['physicalBytes'] > 0, 'PAGE_OR_PHYSICAL_ENCODING')
    for key in ('freePages', 'speculativePages', 'inactivePages', 'activePages', 'fileBackedPages',
                'anonymousPages', 'purgeablePages', 'wiredPages', 'compressorPages'):
        require(sample[key] * sample['pageBytes'] <= sample['physicalBytes'], 'IMPOSSIBLE_' + key)
    require(sample['speculativePages'] <= sample['freePages'], 'IMPOSSIBLE_SPECULATIVE')
    require(0 < sample['beganNs'] < sample['endedNs'] and
            (sample['endedNs'] - sample['beganNs']) / 1e9 <= POLICY['maximumSampleSeconds'], 'SENSOR_TIMING')
    require(sample['pressureBefore'] == sample['pressureAfter'] == POLICY['normalPressure'], 'MEMORY_PRESSURE')
    require(sample['swapUsedBytes'] <= sample['swapUsedBeforeBytes'], 'ACTIVE_SWAP_USAGE')
    return sample


def estimated_available(sample):
    # min() caps a candidate budget; it does NOT identify the intersection of
    # clean inactive file pages. Purgeable and speculative are never added.
    page = sample['pageBytes']
    credit = min(sample['inactivePages'], max(0, sample['fileBackedPages'] - sample['speculativePages']))
    nonwired = max(0, sample['physicalBytes'] - (sample['wiredPages'] + sample['compressorPages']) * page)
    return min((sample['freePages'] + credit) * page, nonwired)


def sdk_files():
    """V3 identity includes executable support code without altering v2 pins."""
    from .. import native
    result = native.code_files()
    for path in sorted((native.SDK_ROOT / 'developer').rglob('*')):
        if '__pycache__' not in path.parts and path.is_file():
            result[str(path.relative_to(native.SDK_ROOT))] = sha(path)
    return result


def assess(samples, runtime=False):
    require(type(samples) is list and len(samples) >= 2, 'TWO_RESOURCE_SAMPLES_REQUIRED')
    mode = 'Runtime' if runtime else 'Admission'
    require(POLICY.get('availabilityMode') == 'TELEMETRY_ONLY'
            and POLICY.get('policyRevision') == 'free-telemetry/0.1', 'AVAILABILITY_POLICY')
    estimates = []
    for sample in samples:
        validate_sample(sample)
        estimates.append(estimated_available(sample))
    for before, after in zip(samples, samples[1:]):
        require(all(before[k] == after[k] for k in ('boot', 'pageBytes', 'physicalBytes')), 'HOST_IDENTITY_CHANGED')
        gap = (after['beganNs'] - before['endedNs']) / 1e9
        require(0 < gap <= POLICY['maximumSampleGapSeconds'] and (runtime or gap >= 0.9), 'RESOURCE_SAMPLE_GAP')
        require(all(after[k] == before[k] for k in ('swapInPages', 'swapOutPages')), 'SWAP_ACTIVITY_OR_COUNTER_REGRESSION')
        require(after['swapUsedBeforeBytes'] <= before['swapUsedBytes'], 'ACTIVE_SWAP_USAGE')
        require(all(after[k] >= before[k] for k in ('compressions', 'decompressions')), 'VM_COUNTER_REGRESSION')
    return dict(status='PASS', profile=PROFILE, experimental=True, reservedMemory=False,
                policyRevision=POLICY['policyRevision'], availabilityMode=POLICY['availabilityMode'],
                availabilityAdmissionEnforced=False,
                minimumEstimatedAvailableBytes=min(estimates), requiredEstimatedBytes=0,
                requiredImmediateFreeBytes=0,
                minimumImmediateFreeBytes=min(s['freePages'] * s['pageBytes'] for s in samples),
                reserveModel=POLICY['reserveModel'], cleanInactiveIntersectionMeasured=False,
                mode='runtime' if runtime else 'admission', qualifiedScientificAdmission=False)


def capture_sensor(sensor, directory):
    from .. import native
    native.guards()
    from case_sdk.common import portable, REPO
    prior = portable.guards.WS
    try:
        portable.guards.WS = REPO
        result, stdout, stderr = portable.guards.capture([str(sensor)], directory, POLICY['sensorProcessWallSeconds'], 8192, 8192)
    finally:
        portable.guards.WS = prior
    require(not result['stop'] and result['ownedChildReaped'] and result['exitCode'] == 0
            and not stderr and len(stdout) < 8192, 'RESOURCE_SENSOR_FAILED')
    return validate_sample(strict(stdout))


def admission(sensor, directory):
    directory.mkdir()
    samples = []
    try:
        samples.append(capture_sensor(sensor, directory / 'sample-0'))
        time.sleep(POLICY['admissionSpacingSeconds'])
        samples.append(capture_sensor(sensor, directory / 'sample-1'))
        return assess(samples), samples
    finally:
        save(directory / 'SAMPLES.json', samples)


class RuntimeGuard:
    def __init__(self, sensor, directory, previous):
        self.sensor, self.directory, self.previous = sensor, directory, previous
        self.last, self.count = 0.0, 0
        directory.mkdir()

    def poll(self, force=False):
        if not force and time.monotonic() - self.last < POLICY['runtimeSampleSpacingSeconds']:
            return
        try:
            current = capture_sensor(self.sensor, self.directory / str(self.count))
            assess([self.previous, current], runtime=True)
            self.previous, self.last = current, time.monotonic()
            self.count += 1
        except BaseException as error:
            save(self.directory / 'STOP.json', dict(cause=str(error), sample=self.count))
            raise


def supervise(raw, out, sensor, previous):
    from .. import native
    native.guards()
    from case_sdk.common import portable
    from sdk_alpha_v2.kit import sample_developer
    guard = RuntimeGuard(sensor, out / 'runtime/HOST_RUNTIME', previous)
    guards = portable.guards
    original, old_root = guards.sample_owned, guards.ROOT
    try:
        guards.sample_owned = lambda proc: sample_developer(proc, original, guard, out / 'runtime')
        guards.ROOT = out
        return guards.monitored(raw, out / 'runtime', portable.LIMITS)
    finally:
        guards.sample_owned, guards.ROOT = original, old_root
