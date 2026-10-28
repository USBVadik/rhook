"""Bounded power/lid capture; raw outputs precede interpretation."""
import re
import time
from developer.files import digest, require, save


def parse(power, lid):
    try:
        power, lid = power.decode('utf-8', errors='strict'), lid.decode('utf-8', errors='strict')
    except UnicodeError as error:
        raise ValueError('HOST_POWER_SENSOR_AMBIGUOUS') from error
    lines = [line for line in power.splitlines() if line.startswith('Now drawing from')]
    sources = re.findall(r"^Now drawing from '(AC Power|Battery Power)'$", power, re.M)
    properties = [line for line in lid.splitlines() if '"AppleClamshellState"' in line]
    lids = re.findall(r'^[\s|]*"AppleClamshellState"\s*=\s*(Yes|No)\s*$', lid, re.M)
    require(len(lines) == len(sources) == 1 and len(properties) == len(lids)
            and lids and len(set(lids)) == 1, 'HOST_POWER_SENSOR_AMBIGUOUS')
    value = dict(onACPower=sources[0] == 'AC Power', lidOpen=lids[0] == 'No')
    require(value['onACPower'] and value['lidOpen'], 'HOST_POWER_LID_NOT_READY')
    return value


def observe(directory):
    from .. import native
    directory.mkdir(mode=0o700)
    outputs = []
    for name, command in [('POWER', ['/usr/bin/pmset', '-g', 'ps']),
                          ('LID', ['/usr/sbin/ioreg', '-r', '-k', 'AppleClamshellState', '-d', '4'])]:
        result, stdout, stderr = native.capture(command, directory / name, 2, 65536, 8192)
        require(result['ownedChildReaped'] and not result['stop'] and result['exitCode'] == 0 and not stderr,
                'HOST_POWER_SENSOR_UNAVAILABLE_' + name)
        outputs.append(stdout)
    value = dict(parse(*outputs), observedUnix=int(time.time()),
                 powerRawSha256=digest(outputs[0]), lidRawSha256=digest(outputs[1]))
    save(directory / 'OBSERVATION.json', value)
    return value
