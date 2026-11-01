"""macOS host admission v4: memory pressure WARN and swap movement are telemetry, not stops.

Separate from v3 (host_v3.py and host_v3_policy.json are unchanged). The same v3 sensor and packet
format are used. What still stops a run:

- CRITICAL memory pressure (4) or an unknown pressure value, at admission or in any runtime sample;
- invalid sensor output: missing or malformed fields, impossible page counts, slow samples;
- a changed boot session, page size or physical memory, a stale or out-of-order sample;
- a decreasing swap-in, swap-out, compression or decompression counter (sensor regression);
- every worker limit, which this module does not touch: sampled RSS <= 1 GiB, CPU and wall
  <= 120 s, stage <= 140 s, workflow <= 180 s, owned process-group cleanup, power and lid.

WARN pressure (2), swap-in/out growth and swap-used changes are recorded in the decision and in
runtime/HOST_RUNTIME/SUMMARY.json. Raw sensor packets stay in the capture directories.
"""
from pathlib import Path
import time
from developer.files import load, require, save, sha, strict
from .host_v3 import COUNTERS, estimated_available, sdk_files

HERE = Path(__file__).resolve().parent
POLICY = load(HERE / 'host_v4_policy.json', 65536)
PROFILE = POLICY['profile']
POLICY_SHA = sha(HERE / 'host_v4_policy.json')
RECORD = 'HOST_V4.json'
MONOTONIC = ('swapInPages', 'swapOutPages', 'compressions', 'decompressions')
__all__ = ['PROFILE', 'POLICY_SHA', 'RECORD', 'validate_sample', 'assess', 'sdk_files',
           'capture_sensor', 'admission', 'RuntimeGuard', 'supervise']


def _policy():
    require(POLICY.get('availabilityMode') == 'TELEMETRY_ONLY'
            and POLICY.get('policyRevision') == 'pressure-telemetry/0.1'
            and POLICY.get('pressureMode') == 'WARN_TELEMETRY_CRITICAL_STOP'
            and POLICY.get('swapMode') == 'TELEMETRY_MONOTONIC_COUNTERS', 'AVAILABILITY_POLICY')


def validate_sample(sample):
    require(type(sample) is dict and all(k in sample for k in (*COUNTERS, 'source', 'platform', 'boot')), 'V4_SENSOR_FIELDS')
    require(sample['source'] == 'DARWIN_HOST_VM64/3' and sample['platform'] == 'darwin-arm64', 'V4_SENSOR_PROFILE')
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
    known = (POLICY['normalPressure'], POLICY['warningPressure'], POLICY['criticalPressure'])
    for key in ('pressureBefore', 'pressureAfter'):
        require(sample[key] in known, 'MEMORY_PRESSURE_ENCODING')
        require(sample[key] != POLICY['criticalPressure'], 'CRITICAL_MEMORY_PRESSURE')
    # Swap used growing within one packet is telemetry in v4 (v3: ACTIVE_SWAP_USAGE).
    return sample


def assess(samples, runtime=False):
    require(type(samples) is list and len(samples) >= 2, 'TWO_RESOURCE_SAMPLES_REQUIRED')
    _policy()
    for sample in samples:
        validate_sample(sample)
    for before, after in zip(samples, samples[1:]):
        require(all(before[k] == after[k] for k in ('boot', 'pageBytes', 'physicalBytes')), 'HOST_IDENTITY_CHANGED')
        gap = (after['beganNs'] - before['endedNs']) / 1e9
        require(0 < gap <= POLICY['maximumSampleGapSeconds'] and (runtime or gap >= 0.9), 'RESOURCE_SAMPLE_GAP')
        # Counters only grow; a decrease means the sensor or the host changed underneath us.
        require(all(after[k] >= before[k] for k in MONOTONIC), 'VM_COUNTER_REGRESSION')
    pressures = [s[k] for s in samples for k in ('pressureBefore', 'pressureAfter')]
    used = [s[k] for s in samples for k in ('swapUsedBeforeBytes', 'swapUsedBytes')]
    first, last = samples[0], samples[-1]
    return dict(status='PASS', profile=PROFILE, experimental=True, reservedMemory=False,
                policyRevision=POLICY['policyRevision'], availabilityMode=POLICY['availabilityMode'],
                pressureMode=POLICY['pressureMode'], swapMode=POLICY['swapMode'],
                availabilityAdmissionEnforced=False, pressureAdmissionEnforced='CRITICAL_ONLY',
                swapActivityAdmissionEnforced=False,
                maximumPressure=max(pressures),
                warningPressureReadings=sum(p == POLICY['warningPressure'] for p in pressures),
                pressureReadings=len(pressures),
                swapInDeltaPages=last['swapInPages'] - first['swapInPages'],
                swapOutDeltaPages=last['swapOutPages'] - first['swapOutPages'],
                swapUsedBytes=dict(first=used[0], last=used[-1], minimum=min(used), maximum=max(used)),
                minimumEstimatedAvailableBytes=min(estimated_available(s) for s in samples),
                requiredEstimatedBytes=0, requiredImmediateFreeBytes=0,
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
        # `first` is the last admission packet; runtime deltas are measured from it.
        self.sensor, self.directory, self.previous, self.first = sensor, directory, previous, previous
        self.last, self.count = 0.0, 0
        self.maximum, self.warnings = None, 0
        directory.mkdir()

    def poll(self, force=False):
        if not force and time.monotonic() - self.last < POLICY['runtimeSampleSpacingSeconds']:
            return
        try:
            current = capture_sensor(self.sensor, self.directory / str(self.count))
            assess([self.previous, current], runtime=True)
            # Only accepted runtime packets count; a stopping packet is reported through STOP.json.
            readings = (current['pressureBefore'], current['pressureAfter'])
            self.maximum = max(readings) if self.maximum is None else max(self.maximum, *readings)
            self.warnings += sum(p == POLICY['warningPressure'] for p in readings)
            self.previous, self.last = current, time.monotonic()
            self.count += 1
        except BaseException as error:
            save(self.directory / 'STOP.json', dict(cause=str(error), sample=self.count))
            raise

    def summary(self):
        """Host telemetry of the runtime window. It is not the run outcome: RESULT.json is."""
        stop = self.directory / 'STOP.json'
        cause = None
        if stop.exists():
            try:
                cause = load(stop, 65536)['cause']
            except (OSError, ValueError, KeyError, TypeError):
                cause = 'STOP_RECORD_UNREADABLE'
        measured = self.count > 0
        return dict(schema='rhook/host-v4-runtime-summary/0.1', profile=PROFILE, policyRevision=POLICY['policyRevision'],
                    scope='HOST_TELEMETRY_ONLY_NOT_RUN_OUTCOME', runtimeSamples=self.count,
                    runtimeTelemetry='MEASURED' if measured else 'NOT_MEASURED',
                    maximumRuntimePressure=self.maximum,
                    warningPressureReadings=self.warnings if measured else None,
                    swapInDeltaPages=self.previous['swapInPages'] - self.first['swapInPages'] if measured else None,
                    swapOutDeltaPages=self.previous['swapOutPages'] - self.first['swapOutPages'] if measured else None,
                    swapUsedBytes=dict(admission=self.first['swapUsedBytes'], last=self.previous['swapUsedBytes']) if measured else None,
                    hostGuardStopped=cause is not None, hostGuardStopCause=cause)


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
        # Worker limits are the unchanged reviewed ones: RSS, CPU, wall, output and cleanup.
        return guards.monitored(raw, out / 'runtime', portable.LIMITS)
    finally:
        guards.sample_owned, guards.ROOT = original, old_root
        try:
            save(out / 'runtime/HOST_RUNTIME/SUMMARY.json', guard.summary())
        except OSError:
            pass  # telemetry only; the supervision result above is authoritative
