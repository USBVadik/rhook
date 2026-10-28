"""Interpret a supervised stage without replacing its first recorded failure.

This is reporting only: no execution, admission, retries or cleanup actions.
Normal bridge closure needs a linked native record; reaping proves termination.
"""
from dataclasses import dataclass
from pathlib import Path
import signal

from developer.files import digest, read, strict


def _record(path, limit):
    info = dict(path=str(path), state='MISSING')
    try:
        raw = read(path, limit)
    except FileNotFoundError:
        return None, info
    except (OSError, ValueError) as error:
        return None, dict(info, state='INVALID', error=type(error).__name__)
    info.update(state='PRESENT', sha256=digest(raw))
    try:
        value = strict(raw)
        if type(value) is not dict:
            raise ValueError('OBJECT_REQUIRED')
        return value, info
    except (ValueError, UnicodeError, RecursionError) as error:
        return None, dict(info, state='INVALID', error=type(error).__name__)


@dataclass
class StageOutcome:
    completion: dict | None
    diagnostics: dict
    primary: dict | None


class NativeStageStop(ValueError):
    def __init__(self, outcome):
        self.report = dict(outcome.diagnostics, primaryStop=outcome.primary)
        self.report['causeCode'] = outcome.primary['kind'] + ': ' + outcome.primary['code']
        super().__init__(self.report['causeCode'])


def inspect_stage(runtime, operation, measured=None):
    """Read only fixed, bounded records from one fresh operation's runtime."""
    runtime = Path(runtime)
    recorded, measured_info = _record(runtime / 'PROCESS_COMPLETION.json', 65536)
    if measured is None:
        measured = recorded
    measured = measured if type(measured) is dict else {}
    host, host_info = _record(runtime / 'HOST_RUNTIME/STOP.json', 65536)
    observer, observer_info = _record(runtime / 'WORKER_OBSERVER_STOP.json', 65536)
    for record, info in ((host, host_info), (observer, observer_info)):
        if record is not None and (type(record.get('cause')) is not str or not record['cause']):
            info.update(state='INVALID', error='STOP_CAUSE_REQUIRED')
    completion, native_info = _record(runtime / 'NATIVE_COMPLETION.json', 8 << 20)
    if completion is not None:
        if completion.get('operationCommitment') != operation or not operation:
            native_info['state'] = 'MISMATCH'
            completion = None
        elif type(completion.get('result')) is not dict:
            native_info['state'] = 'INVALID'
            completion = None
    exit_code = measured.get('exitCode')
    exit_code = exit_code if type(exit_code) is int else None
    worker_exit = dict(code=exit_code, signal=None)
    if exit_code is not None and exit_code < 0:
        try:
            worker_exit['signal'] = signal.Signals(-exit_code).name
        except ValueError:
            worker_exit['signal'] = 'UNKNOWN_SIGNAL'
    terminated = measured.get('workerReaped') is True and exit_code is not None
    bridges = (completion or {}).get('result', {}).get('ownedBridgesClosed')
    diagnostics = dict(nativeCompletion=native_info['state'], workerExit=worker_exit,
        processTermination='CONFIRMED' if terminated else 'UNKNOWN',
        engineBridgeClosure='CONFIRMED' if bridges is True else ('UNCONFIRMED' if bridges is False else 'UNKNOWN'),
        evidencePaths=dict(supervisor=measured_info, hostStop=host_info,
                           observerStop=observer_info, nativeCompletion=native_info),
        stageOperation=operation)
    primary = None
    def stop(kind, code, path):
        return dict(kind=kind, code=str(code)[:400], evidencePath=str(path))
    supervisor_stop = measured.get('stop')
    # A non-generic supervisor stop is sticky (recorded before any later error).
    if supervisor_stop and not str(supervisor_stop).startswith('SUPERVISION_FAILURE_'):
        primary = stop('SUPERVISOR_STOP', supervisor_stop, runtime / 'PROCESS_COMPLETION.json')
    elif host_info['state'] == 'PRESENT':
        primary = stop('HOST_STOP', host['cause'], runtime / 'HOST_RUNTIME/STOP.json')
    elif observer_info['state'] == 'PRESENT':
        primary = stop('HOST_STOP', observer['cause'] or 'WORKER_OBSERVER_STOP', runtime / 'WORKER_OBSERVER_STOP.json')
    elif supervisor_stop:
        primary = stop('SUPERVISOR_STOP', supervisor_stop, runtime / 'PROCESS_COMPLETION.json')
    elif host_info['state'] == 'INVALID' or observer_info['state'] == 'INVALID':
        primary = stop('SUPERVISOR_STOP', 'STOP_RECORD_UNREADABLE', runtime)
    elif not terminated or measured.get('resourcesReliable') is not True:
        primary = stop('SUPERVISOR_STOP', 'SUPERVISION_UNCONFIRMED', runtime / 'PROCESS_COMPLETION.json')
    elif exit_code != 0:
        primary = stop('NATIVE_STOP', 'WORKER_EXIT_NONZERO', runtime / 'PROCESS_COMPLETION.json')
    elif native_info['state'] != 'PRESENT':
        primary = stop('NATIVE_STOP', 'NATIVE_COMPLETION_' + native_info['state'], runtime / 'NATIVE_COMPLETION.json')
    return StageOutcome(completion, diagnostics, primary)


def require_stage(runtime, operation, measured):
    outcome = inspect_stage(runtime, operation, measured)
    if outcome.primary is not None:
        raise NativeStageStop(outcome)
    return outcome.completion


def apply_failure(result, error):
    if isinstance(error, NativeStageStop):
        result.update(error.report)
    else:
        result['causeCode'] = type(error).__name__ + ': ' + str(error)[:1024]


def discovery_cleanup(out):
    """Missing native completion never becomes a successful cleanup claim."""
    out = Path(out)
    if not out.exists():
        return True, dict(processTermination='NOT_STARTED', engineBridgeClosure='NOT_STARTED', nativeCompletion='NOT_STARTED')
    binding, _ = _record(out / 'BINDING.json', 65536)
    operation = (binding or {}).get('operationCommitment')
    diagnostics = inspect_stage(out / 'runtime', operation).diagnostics
    clean = diagnostics['processTermination'] == diagnostics['engineBridgeClosure'] == 'CONFIRMED'
    return clean, diagnostics
