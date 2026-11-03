"""Parameterized Execution developer workflow 0.2: one lpBps from plan to verified result.

    session-plan  (0.1, offline)  choose lpBps; session, variant, static coverage, preparation
    doctor        (read-only)     can this machine run the native supervisor at all?
    session-ready (Stage B)       registration, input authentication, exact operationCommitment
    session-run   (Stage C)       explicit owner consent, one ExecutionSDK.run, then verification
    session-result (read-only)    one result view for baseline and variant

It composes existing pieces only: Counterfactual Session 0.1 (plan, verify_selected) and ExecutionSDK
(register_runtime, register_host, authenticate, operation, run, verify). It adds no execution engine,
supervisor, consent mechanism, proof system or evidence format; the result view is derived from the sealed
verification record and the retained run files. The operation binding, one-shot consent, resource limits,
fail-closed stops and the absence of automatic retries are those of ExecutionSDK.run, unchanged.
"""
import math
import os
import platform
import re
import resource
import signal
import subprocess
import sys
import time
from fractions import Fraction
from pathlib import Path

from developer.files import load, no_links, save, tree

from .core import SessionError, check
from .hookr import DYNAMIC_KIND, LP_BACKEND, OVERLAY_KIND, backend_sdk, dynamic_fee_value
from .plan import BASELINE_LP_BPS, PROFILE, lp_bps_value

DOCTOR_SCHEMA = 'rhook/environment-doctor/0.2'
READY_SCHEMA = 'rhook/parameterized-run-ready/0.2'
RUN_SCHEMA = 'rhook/parameterized-run/0.2'
RESULT_SCHEMA = 'rhook/parameterized-result/0.2'
HOST_PROFILE = 'macos-host-admission-v4'
HOST_RECORD = 'HOST_V4.json'
# The supervisor's own worker query (engine/repro/portable/legacy_guards.sample_owned).
PS_FIELDS = 'pid=,ppid=,pgid=,rss=,comm='
PROBE_CHILD = ('/bin/sleep', '5')
WORLDS = ('SCENARIO_BASELINE', 'SCENARIO_VARIANT')
MEASURE = 'ACTOR_TARGET_TOKEN_TRANSFER_EVENT_NET_IN_SUBJECT_RECEIPT'
OPERATION = re.compile('[0-9a-f]{64}')


# ----- doctor: read-only environment capability check -------------------------------------------

def parse_ps(returncode, stdout, pid, parent):
    """Parse the supervisor's ps row for one owned child; raise ValueError when it is not exactly that child."""
    rows = stdout.strip().splitlines()
    if returncode != 0 or len(rows) != 1:
        raise ValueError(f'PROCESS_TELEMETRY_ROWS: exit {returncode}, {len(rows)} rows')
    cells = rows[0].strip().split(None, 4)
    if len(cells) != 5 or not all(c.isdigit() for c in cells[:4]):
        raise ValueError('PROCESS_TELEMETRY_FORMAT')
    row = dict(pid=int(cells[0]), ppid=int(cells[1]), pgid=int(cells[2]), rssBytes=int(cells[3]) * 1024, executable=cells[4])
    if (row['pid'], row['ppid'], row['pgid']) != (pid, parent, pid) or row['rssBytes'] <= 0:
        raise ValueError('PROCESS_TELEMETRY_IDENTITY')
    return row


def _reap(child):
    if child.poll() is None:
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=5)
    try:
        os.killpg(child.pid, 0)
        return False
    except ProcessLookupError:
        return True
    except PermissionError:
        return False


def telemetry():
    """Start a harmless child the way the supervisor starts its worker, read it with the supervisor's ps query, reap it."""
    def caps():
        resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    child, row, error, gone = None, None, None, None
    try:
        child = subprocess.Popen(list(PROBE_CHILD), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True, preexec_fn=caps)
        time.sleep(0.2)
        p = subprocess.run(['/bin/ps', '-p', str(child.pid), '-o', PS_FIELDS], capture_output=True, text=True, timeout=2)
        row = parse_ps(p.returncode, p.stdout, child.pid, os.getpid())
    except Exception as e:  # PermissionError where an app or agent sandbox forbids /bin/ps
        error = f'{type(e).__name__}: {e}'[:300]
    finally:
        if child is not None:
            gone = _reap(child)
    return dict(ok=error is None and gone is True, row=row, error=error, childReaped=gone)


def power_and_lid():
    """AC power and an open lid, read with the installed power parser over the same read-only commands as a run."""
    from ..cases.scenario import power
    pm = subprocess.run(['/usr/bin/pmset', '-g', 'ps'], stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
    lid = subprocess.run(['/usr/sbin/ioreg', '-r', '-k', 'AppleClamshellState', '-d', '4'], stdin=subprocess.DEVNULL,
                         capture_output=True, timeout=10)
    return power.parse(pm.stdout, lid.stdout)


def doctor(sdk):
    """Can this machine run the installed native supervisor? Read-only: no worker, sensor, consent or network."""
    checks = []

    def add(name, ok, detail, next_step):
        checks.append(dict(check=name, ok=bool(ok), detail=detail, nextStep=None if ok else next_step))

    machine = f'{sys.platform} {platform.machine()}'
    add('platform', sys.platform == 'darwin' and platform.machine() == 'arm64', machine,
        'Native execution of this profile requires macOS arm64.')
    add('privileges', os.geteuid() != 0, dict(uid=os.getuid(), euid=os.geteuid()), 'Run as your own user, not root.')
    t = telemetry()
    add('processTelemetry', t['ok'], t['row'] if t['ok'] else dict(error=t['error'], childReaped=t['childReaped']),
        'The native supervisor samples its worker with /bin/ps. This environment does not allow it (typically an app '
        'or agent sandbox). Run the command from a regular macOS Terminal; nothing was consumed.')
    try:
        value, ok = power_and_lid(), True
    except Exception as e:
        value, ok = dict(error=f'{type(e).__name__}: {e}'[:300]), False
    add('powerAndLid', ok, value, 'Connect AC power and open the lid before a run.')
    caps = sdk.capabilities()
    registration = dict(runtime='REGISTERED' if caps['runtime']['configured'] else 'NOT_REGISTERED',
                        components={n: c['validation'] for n, c in caps['components'].items()},
                        hostAdmission=caps['host']['admissionProfiles'][HOST_PROFILE]['validation'])
    ready = all(c['ok'] for c in checks)
    return dict(schema=DOCTOR_SCHEMA, status='READY' if ready else 'BLOCKED', checks=checks, registration=registration,
                performed=dict(probeChild=' '.join(PROBE_CHILD), nativeWorker=0, sensor=0, consent=0, attemptMarker=0, networkRequests=0),
                meaning='READY means the supervisor can observe its worker here, on AC power with the lid open. Host memory '
                        'admission is decided by the run itself; registration is reported, not required here.')


# ----- variant selection ------------------------------------------------------------------------

def _variant(session, variant_id, lp_bps, dynamic_fee=None):
    check((variant_id is not None and lp_bps is None and dynamic_fee is None) or (variant_id is None and (lp_bps is not None or dynamic_fee is not None)),
          'VARIANT_SELECTION', 'Name the variant by --variant, or by --lp-bps and/or --dynamic-fee (both together select the combined set).')
    views = session.variants()
    if variant_id is not None:
        found = [v for v in views if v['variantId'] == variant_id]
    elif lp_bps is not None and dynamic_fee is not None:
        wanted = dict(lpBps=lp_bps_value(lp_bps), dynamicFee=dynamic_fee_value(dynamic_fee))
        found = [v for v in views if v['descriptor'].get('kind') == OVERLAY_KIND and v['descriptor'].get('replacement') == wanted]
    elif lp_bps is not None:
        lp = lp_bps_value(lp_bps)
        found = [v for v in views if v['descriptor'].get('kind') not in (DYNAMIC_KIND, OVERLAY_KIND) and v['descriptor'].get('replacement') == lp]
    else:
        value = dynamic_fee_value(dynamic_fee)
        found = [v for v in views if v['descriptor'].get('kind') == DYNAMIC_KIND and v['descriptor'].get('replacement') == value]
    check(len(found) == 1, 'VARIANT_NOT_PLANNED', 'Plan this variant first with session-plan; nothing was written.',
          dict(variantId=variant_id, lpBps=lp_bps, dynamicFee=dynamic_fee))
    return found[0]


def _backend(sdk, view):
    """The SDK home that registers, binds, runs and verifies this variant (the derivative's own for Dynamic Fee)."""
    return backend_sdk(sdk.home, view['descriptor'])


def _expected_runtime_profile(view):
    return view['descriptor'].get('backendProfile') if view['descriptor'].get('kind') in (DYNAMIC_KIND, OVERLAY_KIND) else LP_BACKEND


def _selector(view):
    d = view['descriptor']
    if d.get('kind') == OVERLAY_KIND:
        return ['--variant', view['variantId']]
    return ['--dynamic-fee', d['replacement']] if d.get('kind') == DYNAMIC_KIND else ['--lp-bps', str(d['replacement'])]


def _prepared(session, view):
    check(view['preparation'] is not None, 'VARIANT_NOT_PREPARED', 'Run session-plan for this lpBps first.')
    return session.directory / view['preparation']['preparedDirectory']


def _runnable(view):
    check(view['status'] == 'PREPARED_NOT_EXECUTED', 'VARIANT_NOT_RUNNABLE',
          'Only a prepared, never verified variant can be run. A verified variant keeps its first run; read it with session-result.',
          dict(status=view['status'], nextRequirement=view.get('nextRequirement')))


# ----- ready: Stage B in one call ---------------------------------------------------------------

def _register(sdk, runtime, sensor, profile):
    """Use the home's registration unchanged, or register the given reviewed files once.
    profile: the runtime profile this variant needs (the LP worker or the Dynamic Fee OFF derivative)."""
    out = {}
    record = sdk.home / 'scenarios/RUNTIME.json'
    if record.exists():
        if runtime is not None:
            check(load(no_links(runtime), 2 << 20) == load(record, 2 << 20)['runtime'], 'RUNTIME_REGISTRATION_DIFFERS',
                  'This home already has a different registered runtime. Use it unchanged, or a new home.')
        check(load(record, 2 << 20)['runtime'].get('profile') == profile, 'RUNTIME_PROFILE_MISMATCH',
              f'This variant needs a runtime with profile {profile}.')
        out['runtime'] = 'ALREADY_REGISTERED'
    else:
        check(runtime is not None, 'NATIVE_RUNTIME_MISSING',
              f'Pass --runtime with the reviewed runtime manifest for profile {profile} (worker, node and sensor paths '
              'with SHA-256). Nothing is downloaded.', dict(profile=profile))
        check(load(no_links(runtime), 2 << 20).get('profile') == profile, 'RUNTIME_PROFILE_MISMATCH',
              f'This variant needs a runtime with profile {profile}; the given manifest names another. Nothing was registered.')
        sdk.register_runtime(runtime)
        out['runtime'] = 'REGISTERED_NOW'
    host = sdk.home / 'scenarios' / HOST_RECORD
    if host.exists():
        if sensor is not None:
            check(load(host, 65536)['sensor']['path'] == str(no_links(sensor)), 'HOST_REGISTRATION_DIFFERS',
                  'This home already has a different registered host sensor. Use it unchanged, or a new home.')
        out['hostAdmission'] = 'ALREADY_REGISTERED'
    else:
        check(sensor is not None, 'HOST_ADMISSION_NOT_REGISTERED',
              f'Pass --sensor with the reviewed host sensor for {HOST_PROFILE}.')
        sdk.register_host(sensor, profile=HOST_PROFILE)
        out['hostAdmission'] = 'REGISTERED_NOW'
    return out


def _closed(sdk, operation, output_path):
    marker = sdk.home / 'scenarios/execution-attempts' / f'{operation}.json'
    return dict(attemptMarker=marker.exists(), outputPath=Path(output_path).exists())


def ready(sdk, session_id, *, variant_id=None, lp_bps=None, dynamic_fee=None, runtime=None, sensor=None):
    """Stage B for one planned variant: registration, input authentication and the exact operation.

    Runs the worker's identity and input checks (native processes, no EVM). Creates no consent, attempt
    marker or run directory.
    """
    session = sdk.open_session(session_id, profile=PROFILE)
    view = _variant(session, variant_id, lp_bps, dynamic_fee)
    _runnable(view)
    prepared = _prepared(session, view)
    backend = _backend(sdk, view)
    registration = _register(backend, runtime, sensor, _expected_runtime_profile(view))
    auth = backend.authenticate(prepared)
    check(auth.get('status') == 'AUTHENTICATED_SCENARIO_INPUT' and auth.get('scenarioCommitment') == view['preparation']['scenarioCommitment'],
          'PREPARED_INPUT_NOT_AUTHENTICATED', 'The native input check did not authenticate this prepared input; nothing was bound.',
          dict(status=auth.get('status')))
    op = backend.operation(prepared, host_profile=HOST_PROFILE)
    binding, commitment = op['binding'], op['operationCommitment']
    closed = _closed(backend, commitment, op['outputPath'])
    environment = doctor(backend)
    d = view['descriptor']
    if any(closed.values()):
        status = 'OPERATION_CLOSED'
        nxt = dict(step='This exact operation was already attempted in this home and stays closed. A new attempt needs a new home and plan.')
    else:
        status = 'RUN_READY' if environment['status'] == 'READY' else 'RUN_READY_ENVIRONMENT_BLOCKED'
        nxt = dict(step='Review the operation, then run it once from a regular macOS Terminal.',
                   command=['rhook-cases', '--home', str(sdk.home), 'session-run', '--session', session.id, *_selector(view),
                            '--operation', commitment, '--local-owner', '--mac-ready'],
                   meaning='Starting it closes this operation permanently, whatever the result. There is no retry.')
    if d.get('kind') == OVERLAY_KIND:
        selection = dict(interventions=d['interventions'], **d['replacement'], baseline=d['original'], backendHome=str(backend.home))
    elif d.get('kind') == DYNAMIC_KIND:
        selection = dict(dynamicFee=d['replacement'], baselineDynamicFee=d['original'], backendHome=str(backend.home))
    else:
        selection = dict(selectedLpBps=d['replacement'], baselineLpBps=BASELINE_LP_BPS)
    return dict(schema=READY_SCHEMA, status=status, sessionId=session.id, variantId=view['variantId'], **selection,
                scenarioCommitment=view['preparation']['scenarioCommitment'],
                scenarioSha256=view['preparation']['scenarioSha256'], operationCommitment=commitment, outputPath=op['outputPath'],
                binding={k: binding.get(k) for k in ('planId', 'binarySha256', 'sourceCommitment', 'policySha256', 'profile',
                                                     'maximumInvocations', 'RPC', 'WSS', 'automaticRetry', 'externalDelivery')}
                | dict(hostAdmission=dict(profile=binding['hostAdmission']['profile'], policySha256=binding['hostAdmission']['policySha256'])),
                registration=registration, authentication=auth['status'], closed=closed, environment=environment,
                consent='NOT_CREATED', attemptMarker='NOT_CREATED' if not closed['attemptMarker'] else 'EXISTS',
                nativeProcessesRun=['worker identity check', 'worker input authentication'], evmExecutions=0, next=nxt)


# ----- run: Stage C, then verification ----------------------------------------------------------

def _execution_summary(result):
    native = result.get('nativeResult') or {}
    keys = ('status', 'rawTerminal', 'producerInvocations', 'RPC', 'WSS', 'cleanupConfirmed', 'resources')
    return dict(status=result['status'], causeCode=result.get('causeCode'), runDirectory=result.get('runDirectory'),
                cleanupConfirmed=result.get('cleanupConfirmed'), native={k: native.get(k) for k in keys} if native else None)


def run(sdk, session_id, *, operation, local_owner=False, mac_ready=False, variant_id=None, lp_bps=None, dynamic_fee=None, evidence=None):
    """One native execution of one reviewed operation, then the existing verification. Never retried."""
    # Consent first, as in ExecutionSDK.run: no input, process or authority access before it.
    check(local_owner is True and mac_ready is True, 'EXACT_LOCAL_CONSENT_REQUIRED',
          'Review the exact operation, confirm AC power and an open lid, and pass --local-owner --mac-ready.')
    check(type(operation) is str and OPERATION.fullmatch(operation) is not None, 'OPERATION_COMMITMENT_REQUIRED',
          'Pass the exact 64-hex operationCommitment from session-ready.')
    session = sdk.open_session(session_id, profile=PROFILE)
    view = _variant(session, variant_id, lp_bps, dynamic_fee)
    _runnable(view)
    prepared = _prepared(session, view)
    backend = _backend(sdk, view)
    environment = doctor(backend)
    d = view['descriptor']
    selection = (dict(interventions=d['interventions'], **d['replacement']) if d.get('kind') == OVERLAY_KIND
                 else dict(dynamicFee=d['replacement']) if d.get('kind') == DYNAMIC_KIND else dict(selectedLpBps=d['replacement']))
    base = dict(schema=RUN_SCHEMA, sessionId=session.id, variantId=view['variantId'], **selection,
                operationCommitment=operation, environment=environment, automaticRetry=False)
    if environment['status'] != 'READY':
        return dict(base, status='RUN_STOP_ENVIRONMENT_NOT_READY', operationPermanentlyClosed=False,
                    consumed=dict(consent=False, attemptMarker=False),
                    nextStep='Nothing was consumed. Fix the failed doctor checks, then run the same command again from a regular Terminal.')
    evidence = no_links(evidence) if evidence is not None else sdk.home.parent / f'{sdk.home.name}-evidence' / operation
    execution = backend.run(prepared, operation=operation, evidence=evidence, local_owner=True, mac_ready=True, host_profile=HOST_PROFILE)
    base.update(evidenceDirectory=str(evidence), operationPermanentlyClosed=True, execution=_execution_summary(execution))

    def finish(value):
        if evidence.is_dir():
            save(evidence / 'DEVELOPER_RUN.json', value)
        return value

    if execution['status'] != 'EXECUTION_COMPLETED':
        return finish(dict(base, status='RUN_STOP', causeCode=execution.get('causeCode'),
                           nextStep=execution.get('nextStep') or 'Preserve the evidence. This operation is closed and is not retried.'))
    run_dir = Path(execution['runDirectory'])
    try:
        verified = backend.verify(run_dir)
        check(verified.get('status') == 'SCENARIO_RECORDED_INTEGRITY_PASS', 'RECORDED_INTEGRITY_NOT_PASSED',
              'The existing verifier did not pass the retained run.', dict(status=verified.get('status')))
        record = session.verify_selected(view['variantId'], run_dir)
        card = result(sdk, session.id, variant_id=view['variantId'])
    except (SessionError, ValueError, OSError, KeyError, TypeError) as error:
        return finish(dict(base, status='RUN_COMPLETED_VERIFICATION_STOP', causeCode=getattr(error, 'code', None) or f'{type(error).__name__}: {error}'[:400],
                           nextStep='The native run completed and stays closed. Inspect the retained run; verification is not retried automatically.'))
    return finish(dict(base, status='RUN_VERIFIED',
                       verification=dict(executionVerify=verified['status'], sessionVerification=record['status'],
                                         verificationCommitment=record['verificationCommitment']),
                       result=card))


# ----- result: one view of a verified variant ---------------------------------------------------

def _recorded_run(run_dir, record):
    """Roots and balances from the retained run, after checking it against its own manifest and the verification."""
    if not run_dir.is_dir():
        return dict(status='RUN_DIRECTORY_NOT_AVAILABLE', worlds={})
    manifest = load(run_dir / 'MANIFEST.json', 2 << 20)
    check(tree(run_dir, omit=('MANIFEST.json',)) == manifest['files'], 'RUN_RECORD_DRIFT',
          'The retained run no longer matches its manifest; the result view is not built from it.')
    res = load(run_dir / 'RESULT.json', 1 << 20)
    final = load(run_dir / 'runtime/scenario/FINAL.json', 8 << 20)
    check(res.get('status') == 'SCENARIO_COMPLETED' and res.get('operationCommitment') == record['run']['operationCommitment']
          and final.get('scenarioCommitment') == record['run']['scenarioCommitment']
          and [w.get('world') for w in final.get('worlds', [])] == list(WORLDS), 'RUN_RECORD_NOT_THIS_VERIFICATION',
          'The run directory does not hold the run named by the verification record.')
    worlds = {w['world']: dict(stateRoot=w.get('stateRoot'), receiptsRoot=w.get('receiptsRoot'),
                               actorBalanceBeforeWei=w.get('actorBalanceBefore'), actorBalanceAfterWei=w.get('actorBalanceAfter'))
              for w in final['worlds']}
    return dict(status='MATCHES_MANIFEST_AND_VERIFICATION', worlds=worlds, evidenceCommitment=final.get('evidenceCommitment'),
                originalWitnessCommitment=final['worlds'][0].get('originalWitnessCommitment'))


def percent(delta, base):
    """Exact signed percentage, rounded half-up to 4 decimals, as text."""
    if base == 0:
        return None
    value = Fraction(delta * 100, base)
    scaled = math.floor(abs(value) * 10000 + Fraction(1, 2))
    sign = '-' if value < 0 else '+'
    return f'{sign}{scaled // 10000}.{scaled % 10000:04d}'


def result(sdk, session_id, *, variant_id=None, lp_bps=None, dynamic_fee=None):
    """Baseline and variant of one verified variant side by side. Read-only; runs no process."""
    session = sdk.open_session(session_id, profile=PROFILE)
    view = _variant(session, variant_id, lp_bps, dynamic_fee)
    record = session._verification(view['variantId'])
    check(record is not None, 'VARIANT_NOT_VERIFIED', 'There is no verified run for this variant yet: session-ready, then session-run.',
          dict(status=view['status']))
    plan_id = load(_prepared(session, view) / 'PREPARATION.json', 65536)['planId']
    recorded = _recorded_run(_backend(sdk, view).home / 'scenarios/runs' / plan_id, record)
    comparison = record['comparison']
    worlds = {w['world']: w for w in comparison['worlds']}
    descriptor = view['descriptor']
    dynamic = descriptor.get('kind') == DYNAMIC_KIND
    overlay = descriptor.get('kind') == OVERLAY_KIND
    rows = []
    for name, setting in zip(WORLDS, (descriptor['original'], descriptor['replacement'])):
        w = worlds[name]
        world_setting = dict(setting) if overlay else dict(lpBps=BASELINE_LP_BPS, dynamicFee=setting) if dynamic else dict(lpBps=setting)
        rows.append(dict(world=name, **world_setting, receiptStatus=w['receiptStatus'], gasUsed=w['gasUsed'],
                         outerSwapFeePips=w.get('outerSwapFeePips'),
                         actorTargetTokenTransferNetBaseUnits=w['actorTargetTokenTransferNetBaseUnits'],
                         **recorded['worlds'].get(name, {})))
    base, variant = (int(r['actorTargetTokenTransferNetBaseUnits']) for r in rows)
    production = record['status'] == 'RECORDED_RUN_VERIFIED'
    return dict(schema=RESULT_SCHEMA, status='VERIFIED_RESULT' if production else 'TEST_ONLY_NOT_EVIDENCE',
                profile=PROFILE, sessionId=session.id, variantId=view['variantId'], checkpoint=session.header['checkpoint'],
                parameter=dict(field=descriptor.get('field'), baseline=descriptor['original'], variant=descriptor['replacement']),
                measure=comparison.get('measure', MEASURE), worlds=rows,
                difference=dict(targetTokenTransferNetBaseUnits=str(variant - base),
                                relativeToBaselinePercent=percent(variant - base, base),
                                gasUsed=rows[1]['gasUsed'] - rows[0]['gasUsed']),
                commitments=dict(scenarioCommitment=record['run']['scenarioCommitment'], scenarioSha256=record['run']['scenarioSha256'],
                                 operationCommitment=record['run']['operationCommitment'],
                                 verificationCommitment=record['verificationCommitment'],
                                 evidenceCommitment=recorded.get('evidenceCommitment'),
                                 originalWitnessCommitment=recorded.get('originalWitnessCommitment')),
                verification=dict(status=record['status'], backend=record['backend'], runRecord=recorded['status'], **record['assurance']),
                limitations=session.header['limitations'],
                meaning='Net Transfer-event amount of the target token to the actor in the subject receipt of each world. '
                        'It is not profit and not a final balance.')


def render(card):
    """Plain-text view of a result card for a terminal."""
    def short(v):
        return v if not isinstance(v, str) or len(v) <= 20 else v[:10] + '...' + v[-6:]
    b, v = card['worlds']
    p = card['parameter']
    def column(world):
        if 'dynamicFee' in world and world.get('lpBps', BASELINE_LP_BPS) != BASELINE_LP_BPS:
            return f"LP{world['lpBps']} + DF {world['dynamicFee']}"
        return f"Dynamic Fee {world['dynamicFee']}" if 'dynamicFee' in world else f"LP{world['lpBps']}"
    lines = [f"RHOOK parameterized result: {card['status']}",
             f"{p['field']}: baseline {p['baseline']} -> variant {p['variant']}   session {short(card['sessionId'])}",
             f"{'':28}{column(b) + ' (baseline)':>28}{column(v) + ' (variant)':>28}"]
    for label, key in (('receipt status', 'receiptStatus'), ('gas used', 'gasUsed'), ('outer swap fee (pips)', 'outerSwapFeePips'),
                       ('target-token net (base units)', 'actorTargetTokenTransferNetBaseUnits'), ('state root', 'stateRoot'),
                       ('receipts root', 'receiptsRoot')):
        fmt = lambda x: ','.join(map(str, x)) if isinstance(x, list) else short(x) if key.endswith('Root') else str(x)
        lines.append(f"{label:28}{fmt(b.get(key)):>28}{fmt(v.get(key)):>28}")
    d, c, ver = card['difference'], card['commitments'], card['verification']
    lines += [f"difference: {int(d['targetTokenTransferNetBaseUnits']):+d} base units ({d['relativeToBaselinePercent']}%), gas {d['gasUsed']:+d}",
              f"operation {c['operationCommitment']}", f"verification {c['verificationCommitment']}",
              f"checked by: {ver['verification']}; run record: {ver['runRecord']}",
              f"not established: independent EVM re-execution, economic assurance ({ver['economicAssurance']}), qualified claims ({ver['qualifiedClaims']})",
              card['meaning']]
    return '\n'.join(lines)
