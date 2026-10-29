"""RTL arithmetic/rail checks plus independent controller transfer-function checks.

PI/PII/PIII use cascaded PI factors. A full-rate proportional path is compared
with half-rate integral recurrence, then against the expected continuous-time
controller well below the 122.88 MHz integral sampling rate. No optical hardware.
"""
from pathlib import Path
import json
import subprocess
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'TransportPhaseLockFF.srcs/sources_1/new/intensity_compensator.sv'
WORK = ROOT / 'build/intensity_linearized/compensator_test'
BIN = Path('/home/levlabcukomen/tools/Vivado/2024.1/bin')
FS_HZ = 245.76e6
STATE_LIMIT = 1 << 49
SIGNAL_LIMIT = 1 << 25


def bounded(value, limit):
    return min(limit - 1, max(-limit, int(value)))


def fixed_model(rows):
    """Independent sequential model retaining full multiplier precision."""
    states = [0, 0, 0]
    increments = [0, 0, 0]
    integral_inputs = [0, 0, 0]
    input_hold = 0
    integral_sums = [0, 0, 0]
    phase = sample_hold = state_clip = 0
    product = p_valid = input_clip = p_out = p_out_valid = p_clip = 0
    lag_state = lag_phase = lag_valid_d = lag_product = lag_input = 0
    shelf_product = lag_out = lag_valid = lag_clip = 0
    result = []
    for row in rows:
        (reset_n, enabled, reset, held, valid, error, order, kp,
         a1, a2, a3, ll, ll_alpha, ll_gain, high, low) = row
        # Shelf sees the proportional path's preceding registered output.
        if not reset_n or reset or not enabled or not valid or not p_out_valid:
            lag_state = lag_phase = lag_valid_d = lag_product = lag_input = 0
            shelf_product = lag_out = lag_valid = lag_clip = 0
        else:
            difference = p_out - ((lag_state + (1 << 23)) >> 24)
            y = lag_input + ((shelf_product + (1 << 11)) >> 12)
            lag_out = bounded(y, SIGNAL_LIMIT)
            lag_valid = lag_valid_d
            lag_clip = not -SIGNAL_LIMIT <= y < SIGNAL_LIMIT
            shelf_product = difference * (ll_gain - 4096)
            lag_input = p_out
            lag_valid_d = 1
            if lag_phase == 0:
                lag_product = difference * min(ll_alpha, 1 << 30)
            else:
                lag_state = bounded(lag_state + (lag_product >> 6), STATE_LIMIT)
            lag_phase ^= 1

        if not reset_n or not enabled or reset or not valid:
            states = [0, 0, 0]
            increments = [0, 0, 0]
            integral_inputs = [0, 0, 0]
            input_hold = 0
            integral_sums = [0, 0, 0]
            phase = sample_hold = state_clip = 0
            product = p_valid = input_clip = p_out = p_out_valid = p_clip = 0
        else:
            rounded = (product + 2048) >> 12
            x0 = bounded(rounded, SIGNAL_LIMIT)
            x = [x0, x0+integral_sums[0], x0+integral_sums[1]]
            selected = x0+integral_sums[2]
            state_signals = [bounded((state + (1 << 23)) >> 24, SIGNAL_LIMIT) for state in states]
            integral_sums = [state_signals[0], sum(state_signals[:2]),
                             sum(state_signals[:order if order in (2, 3) else 1])]
            p_out = bounded(selected, SIGNAL_LIMIT)
            p_out_valid = p_valid
            p_clip = (not -SIGNAL_LIMIT <= selected < SIGNAL_LIMIT or
                      not -SIGNAL_LIMIT <= rounded < SIGNAL_LIMIT)
            product = error * kp
            p_valid = 1
            input_clip = not -SIGNAL_LIMIT <= selected < SIGNAL_LIMIT
            if phase == 0:
                increments = [integral_inputs[j] * a
                              for j, a in enumerate((a1, a2, a3))]
                sample_hold = held or input_hold
            else:
                state_clip = False
                for j, delta in enumerate(increments):
                    direction = np.sign(delta)
                    integrate = (not sample_hold and not held and kp != 0 and
                                 not (high and direction > 0) and
                                 not (low and direction < 0))
                    if integrate and j < max(1, order):
                        candidate = states[j] + delta
                        state_clip |= not -STATE_LIMIT <= candidate < STATE_LIMIT
                        states[j] = bounded(candidate, STATE_LIMIT)
            if order < 2:
                states[1] = 0
            if order != 3:
                states[2] = 0
            integral_inputs = [bounded(x[j], SIGNAL_LIMIT) for j in range(3)]
            input_hold = held
            phase ^= 1
        result.append([lag_out if ll else p_out, lag_valid if ll else p_out_valid,
                       state_clip or p_clip or (ll and lag_clip), *states,
                       phase, p_out, lag_state])
    return np.asarray(result, dtype=np.int64)


def stimulus():
    rows, sections = [], {}
    defaults = dict(rst_n=1, enable=1, reset=0, hold=0, valid=1, error=256,
                    order=1, kp=4096, a1=0, a2=0, a3=0, ll=0,
                    ll_alpha=1000000, ll_gain=4096, high=0, low=0)

    def append(name, errors, **settings):
        config = dict(defaults, **settings)
        for _ in range(4):
            rows.append(list(dict(defaults, rst_n=0, enable=0).values()))
        first = len(rows)
        for error in errors:
            rows.append(list(dict(config, error=int(error)).values()))
        sections[name] = [first, len(rows)]

    rng = np.random.default_rng(445)
    append('pure_p', rng.integers(-20000000, 20000000, 2048), kp=3021)
    for order in (1, 2, 3):
        append(f'order{order}', np.full(4096, 256), order=order,
               a1=100000, a2=1000, a3=100)
        append(f'rail_high_positive{order}', np.full(1000, 25600), order=order,
               a1=100000, a2=1000, a3=100, high=1)
        append(f'rail_low_negative{order}', np.full(1000, -25600), order=order,
               a1=100000, a2=1000, a3=100, low=1)
    append('hold', np.full(1000, 25600), hold=1, a1=100000)
    append('negative_kp_blocked', np.full(1000, 25600), kp=-4096, low=1, a1=100000)
    append('negative_kp_unwind', np.full(1000, 25600), kp=-4096, high=1, a1=100000)
    append('state_saturation', np.full(4000, SIGNAL_LIMIT-1), a1=(1 << 20)-1, order=3,
           a2=(1 << 20)-1, a3=(1 << 20)-1)
    append('negative_state_saturation', np.full(4000, -SIGNAL_LIMIT), a1=(1 << 20)-1, order=3,
           a2=(1 << 20)-1, a3=(1 << 20)-1)
    append('output_saturation', np.full(200, SIGNAL_LIMIT-1), kp=131071)
    append('invalid', np.full(100, 25000), valid=0)
    append('state_reset', np.full(100, 25000), reset=1)
    append('valid_gap', np.full(400, 25600), a1=100000, ll=1, ll_gain=12288)
    first, _ = sections['valid_gap']
    for index in range(first+100, first+104):
        rows[index][4] = 0
    append('hold_loaded', np.full(400, 25600), a1=100000, order=3, a2=1000, a3=100)
    first, _ = sections['hold_loaded']
    for index in range(first+100, first+200):
        rows[index][3] = 1
    append('lag_dc', np.full(18000, 10000*256), ll=1, ll_gain=12288,
           ll_alpha=round((1-np.exp(-2*np.pi*1e5/(FS_HZ/2))) * 2**30))

    # High test frequencies bound unbounded integrator startup transients over
    # a finite record; the phasor fit explicitly includes a cubic drift term.
    for order in (1, 2, 3):
        n = np.arange(49152)
        append(f'phasor{order}', np.rint(200*256*np.cos(2*np.pi*500e3*n/FS_HZ)),
               order=order, kp=2048,
               a1=round(2*np.pi*40e3/(FS_HZ/2)*2**24),
               a2=round(2*np.pi*2e3/(FS_HZ/2)*2**24),
               a3=round(2*np.pi*100/(FS_HZ/2)*2**24))
    n = np.arange(49152)
    append('lag_phasor', np.rint(200*256*np.cos(2*np.pi*500e3*n/FS_HZ)),
           ll=1, ll_gain=12288,
           ll_alpha=round((1-np.exp(-2*np.pi*1e5/(FS_HZ/2))) * 2**30))
    return rows, sections


def phasor(signal, frequency_hz):
    n = np.arange(len(signal))
    angle = 2*np.pi*frequency_hz*n/FS_HZ
    t = np.linspace(-1, 1, len(signal))
    basis = np.column_stack([np.cos(angle), np.sin(angle), t**0, t, t**2, t**3])
    beta = np.linalg.lstsq(basis, signal, rcond=None)[0]
    return beta[0] - 1j*beta[1]


def physical_checks(rows, actual, sections):
    checks = {}
    for name in ('rail_high_positive1', 'rail_high_positive2', 'rail_high_positive3',
                 'rail_low_negative1', 'rail_low_negative2', 'rail_low_negative3',
                 'hold', 'negative_kp_blocked', 'invalid', 'state_reset'):
        a, b = sections[name]
        assert np.all(actual[a:b, 3:6] == 0), name
    a, b = sections['negative_kp_unwind']
    assert actual[b-1, 3] < 0
    a, b = sections['state_saturation']
    assert np.any(actual[a:b, 2])
    assert actual[b-1, 3] == STATE_LIMIT-1
    a, b = sections['negative_state_saturation']
    assert np.any(actual[a:b, 2])
    assert actual[b-1, 3] == -STATE_LIMIT
    a, _ = sections['valid_gap']
    assert np.all(actual[a+100:a+104, :6] == 0)
    a, _ = sections['hold_loaded']
    assert np.all(actual[a+100:a+200, 3:6] == actual[a+99, 3:6])
    a, b = sections['lag_dc']
    assert abs(actual[b-1, 0]/256-10000) < .02
    for order in (1, 2, 3):
        a, b = sections[f'phasor{order}']
        # One-clock from sampled input edge to output edge. Include ZOH timing
        # and the integral scheduling only in tolerance (well under a degree).
        measured = phasor(actual[a+5000:b, 0]/256, 500e3) / phasor(
            np.asarray(rows)[a+5000:b, 5]/256, 500e3)
        expected = .5 * np.prod([1+f/(1j*500e3) for f in (40e3, 2e3, 100)[:order]])
        expected *= np.exp(-2j*np.pi*500e3/FS_HZ)
        # Side-path pipeline delays affect the integral contribution slightly;
        # the separate bit-exact check verifies those delays without tolerance.
        assert abs(measured/expected - 1) < .005, (order, measured, expected)
        checks[f'order{order}_relative_error'] = float(abs(measured/expected-1))
    a, b = sections['lag_phasor']
    measured = phasor(actual[a+5000:b, 0]/256, 500e3) / phasor(
        np.asarray(rows)[a+5000:b, 5]/256, 500e3)
    expected = (1+1j*500e3/(1e5/3))/(1+1j*500e3/1e5)
    expected *= np.exp(-2j*np.pi*500e3*3/FS_HZ)
    assert abs(measured/expected-1) < .01, (measured, expected)
    checks['leadlag_relative_error'] = float(abs(measured/expected-1))
    return checks


def run():
    WORK.mkdir(parents=True, exist_ok=True)
    rows, sections = stimulus()
    expected = fixed_model(rows)
    (WORK/'input.txt').write_text(''.join(' '.join(map(str, row))+'\n' for row in rows))
    for cmd in (['xvlog', '--sv', str(SOURCE), str(ROOT/'tests/intensity_compensator_tb.sv')],
                ['xelab', 'intensity_compensator_tb', '-s', 'controller_sim'],
                ['xsim', 'controller_sim', '-runall']):
        p = subprocess.run([str(BIN/cmd[0]), *cmd[1:]], cwd=WORK, capture_output=True, text=True)
        (WORK/(cmd[0]+'.log')).write_text(p.stdout+p.stderr)
        if p.returncode or 'Fatal:' in p.stdout:
            raise RuntimeError((p.stdout+p.stderr)[-6000:])
    actual = np.loadtxt(WORK/'output.txt', dtype=np.int64)
    bad = np.argwhere(actual != expected)
    assert len(bad) == 0, [(tuple(x), actual[tuple(x)], expected[tuple(x)]) for x in bad[:10]]
    checks = physical_checks(rows, actual, sections)
    checks['bit_exact_clocks'] = len(rows)
    (WORK/'result.json').write_text(json.dumps(checks, indent=2)+'\n')
    print(json.dumps(checks, indent=2))
    print('PASS: controller rails/signs/reset, PI/PII/PIII, unity-DC leadlag, bit-exact states')


if __name__ == '__main__':
    run()
