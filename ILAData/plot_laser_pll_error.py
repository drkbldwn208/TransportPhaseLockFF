#!/usr/bin/env python3
"""Replay an ADC ILA capture through the laser PLL RTL and plot its error output.

Example: python3 ILAData/plot_laser_pll_error.py ILAData/iladata6.ila

Uses ADC 224/3, 1.96608 GS/s, eight real signed samples per clock. The ILA
contains neither PLL control registers nor NCO phase. Controls below are
assumptions unless supplied from the board; NCO phase is set to zero at the
first captured sample. Absolute phase, wrap times and low-amplitude validity
can therefore differ from hardware. No additional filtering is applied.
Outputs are DAC input codes, excluding RFDC interpolation and analog response.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.signal import lfilter, periodogram
from analyze_laser_pll_adc import ADC_RATE_HZ, fit_tone, read_adc_counts, plt


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'TransportPhaseLockFF.srcs/sources_1/new'
ERROR_RATE_HZ = ADC_RATE_HZ/8
PHASE_CODES_PER_TURN = 1 << 18


def signed(value, bits):
    return (value + (1 << (bits-1))) % (1 << bits) - (1 << (bits-1))


def replay(adc_counts, reference_hz, control, offset_code, work, vivado_bin):
    """Replay twice, capture off/on, retaining the actual fixed-point datapath."""
    work.mkdir(parents=True, exist_ok=True)
    shutil.copy(SRC/'laser_pll_sine.mem', work)
    shutil.copy(SRC/'laser_pll_hann.mem', work)
    frequency_word = round(reference_hz/ADC_RATE_HZ*(1 << 48))
    packed_words = [sum((int(value) & 0xffff) << (16*k) for k, value in enumerate(row))
                    for row in adc_counts.reshape(-1, 8)]
    case_length = 8+len(packed_words)+30
    vectors = []
    for capture_on in (False, True):
        for cycle in range(case_length):
            reset = cycle >= 3
            active = cycle >= 8
            valid = 8 <= cycle < 8+len(packed_words)
            packed = packed_words[cycle-8] if valid else 0
            # Load FCW at cycle 3; commit a phase restart at cycle 7 so that
            # the first captured sample at cycle 8 sees reference phase zero.
            high = (frequency_word >> 32) | (1 << (16 if cycle < 7 else 17))
            settings = (control & ~3) | int(active) | (int(capture_on) << 1)
            vectors.append(f'{int(reset):x} {int(valid):x} 1 {packed:032x} '
                           f'{frequency_word & 0xffffffff:08x} {high:08x} '
                           f'{settings:08x} {offset_code & 0x3ffff:x}\n')
    (work/'stimulus.txt').write_text(''.join(vectors))
    # Extend only the temporary testbench trace; leave the normal regression
    # format intact. Filter outputs are signed 24-bit, with 8 fractional bits.
    bench = (ROOT/'tests/laser_pll_tb.sv').read_text()
    bench = bench.replace('"%d %h %h %h %h %h", cycle',
                          '"%d %h %h %h %h %h %h %h", cycle')
    bench = bench.replace('dut.mixer.phase_accumulator,dut.mixer.frequency_word);',
                          'dut.mixer.phase_accumulator,dut.mixer.frequency_word,'
                          'dut.filtered_i,dut.filtered_q);')
    (work/'replay_tb.sv').write_text(bench)
    sources = [str(SRC/f'laser_pll{x}.sv') for x in
               ('_mixer', '_fir', '_cordic', '_unwrap', '_error', '_fft', '_handoff', '_acquisition', '')]
    sources.append(str(SRC/'laser_pll_dac.v'))
    fft_wrapper = ROOT/'TransportPhaseLockFF.srcs/sources_1/ip/laser_pll_fft_core/sim/laser_pll_fft_core.vhd'
    if not fft_wrapper.exists():
        fft_wrapper = ROOT/'TransportPhaseLockFF.gen/sources_1/ip/laser_pll_fft_core/sim/laser_pll_fft_core.vhd'
    commands = [['xvhdl', str(fft_wrapper)],
                ['xvlog', '--sv', '-i', str(SRC), *sources, str(work/'replay_tb.sv')],
                ['xelab', '-L', 'xfft_v9_1_12', 'laser_pll_tb', '-s', 'laser_pll_sim'],
                ['xsim', 'laser_pll_sim', '-runall']]
    for command in commands:
        result = subprocess.run([str(vivado_bin/command[0]), *command[1:]], cwd=work,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (work/f'{command[0]}.log.txt').write_text(result.stdout)
        if result.returncode:
            raise RuntimeError(result.stdout[-5000:])
        print(command[0], 'PASS', flush=True)
    rows = [line.split() for line in (work/'output.txt').read_text().splitlines()]
    assert len(rows) == 2*case_length
    # Omit startup and the end margin. Associate each stage with the same
    # captured ADC word using the independently tested pipeline latencies.
    indices = np.arange(30, len(packed_words)-20)
    cases = []
    for case in range(2):
        data = {key: [] for key in ('i', 'q', 'phase', 'frequency', 'valid', 'dac')}
        for index in indices:
            start = case*case_length+8+index
            iq_row, phase_row, dac_row = rows[start+7], rows[start+15], rows[start+18]
            status = int(phase_row[1], 16)
            data['i'].append(signed(int(iq_row[6], 16), 24)/256)
            data['q'].append(signed(int(iq_row[7], 16), 24)/256)
            data['phase'].append(signed(status, 18)*2*np.pi/PHASE_CODES_PER_TURN)
            data['frequency'].append(signed(int(phase_row[2], 16), 18)*ERROR_RATE_HZ/PHASE_CODES_PER_TURN)
            data['valid'].append(bool(status & (1 << 19)))
            data['dac'].append(signed(int(dac_row[3], 16), 16))
        cases.append({key: np.array(value) for key, value in data.items()})
    # Capture control must not alter the upstream I/Q or phase extraction.
    for key in ('i', 'q', 'phase', 'valid'):
        np.testing.assert_array_equal(cases[0][key], cases[1][key])
    return indices, cases, frequency_word/(1 << 48)*ADC_RATE_HZ


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--adc-slot', type=int, default=11, help='ADC 224/3 ILA slot: 9 in new BD, 11 in old captures')
    parser.add_argument('--reference-hz', type=float, default=800e6)
    parser.add_argument('--control', type=lambda x: int(x, 0), default=(64 << 16) | (6 << 8) | 1)
    parser.add_argument('--phase-offset-code', type=lambda x: int(x, 0), default=0)
    parser.add_argument('--vivado-bin', type=Path, default=Path('/home/levlabcukomen/tools/Vivado/2024.1/bin'))
    args = parser.parse_args()
    if not 0 < args.reference_hz < ADC_RATE_HZ/2 or args.control & 8:
        parser.error('Reference must lie within the first Nyquist zone; clear flag must be off.')
    adc = read_adc_counts(args.capture, args.adc_slot)
    work = Path('/tmp')/f'laser_pll_replay_{args.capture.stem}'
    indices, (phase_only, capture_on), reference_hz = replay(
        adc, args.reference_hz, args.control, args.phase_offset_code, work, args.vivado_bin)
    time_s = indices/ERROR_RATE_HZ
    frequency_hz, coefficients, fit = fit_tone(adc)
    peak_counts = np.hypot(*coefficients[:2])
    gain = 1 << ((args.control >> 4) & 15)
    capture_gain = 1 << ((args.control >> 8) & 15)
    threshold = args.control >> 16

    # Cross-check RTL phase against independent floating-point I/Q/atan2.
    entries = re.findall(r"(\d+): fir_coefficient = (-?)18'sd(\d+);",
                         (SRC/'laser_pll_fir_coeffs.vh').read_text())
    taps = np.array([(-1 if sign else 1)*int(value) for _, sign, value in entries])/131072
    raw_time_s = np.arange(len(adc))/ADC_RATE_HZ
    iq_float = lfilter(taps, [1.0], adc*np.exp(-2j*np.pi*reference_hz*raw_time_s))[7::8][indices]
    expected = args.phase_offset_code*2*np.pi/PHASE_CODES_PER_TURN-np.angle(iq_float)
    phase_difference = (phase_only['phase']-expected+np.pi) % (2*np.pi)-np.pi
    good = phase_only['valid']
    max_error_rad = float(np.max(abs(phase_difference[good]))) if np.any(good) else None
    if max_error_rad is not None:
        assert max_error_rad < 0.005, f'RTL/float phase discrepancy: {max_error_rad} rad'

    frequency, density = periodogram(adc, fs=ADC_RATE_HZ, window='hann', scaling='density')
    # Integrated RF power includes every signal and noise component in this
    # band. It is not a fitted carrier amplitude or an SNR measurement.
    reference_band = abs(frequency-reference_hz) <= 100e6
    band_rms_counts = np.sqrt(np.sum(density[reference_band])*(frequency[1]-frequency[0]))
    result = dict(capture=str(args.capture), sha256=hashlib.sha256(args.capture.read_bytes()).hexdigest(),
                  sample_rate_hz=ADC_RATE_HZ, reference_hz=reference_hz,
                  assumed_control=hex(args.control), assumed_phase_offset_code=args.phase_offset_code,
                  assumed_nco_phase_at_capture_start_rad=0, duration_us=len(adc)/ADC_RATE_HZ*1e6,
                  strongest_fitted_tone_hz=frequency_hz, strongest_fitted_tone_peak_counts=peak_counts,
                  strongest_fitted_tone_dbfs=float(20*np.log10(peak_counts/32768)),
                  raw_peak_counts=float(np.max(abs(adc))), raw_rms_counts=float(np.std(adc)),
                  raw_minimum_counts=float(adc.min()), raw_maximum_counts=float(adc.max()),
                  reference_plus_minus_100mhz_rms_counts=float(band_rms_counts),
                  reference_plus_minus_100mhz_dbfs=float(20*np.log10(band_rms_counts/(32768/np.sqrt(2)))),
                  tone_fit_residual_rms_counts=float(np.std(adc-fit)),
                  mixed_vector_median_counts=float(np.median(np.hypot(phase_only['i'], phase_only['q']))),
                  valid_fraction=float(np.mean(good)), rtl_vs_float_max_phase_error_rad=max_error_rad,
                  note='Strongest-tone fit is not a measure of the 800 MHz beat amplitude. '
                       'Absolute NCO phase and live GPIO settings are not in this ILA. '
                       'DAC traces include validity gating and clipping, but not RFDC/analog filtering.')
    for label, case in (('phase_only', phase_only), ('capture_on', capture_on)):
        result[label] = dict(dac_rms_about_mean_counts=float(np.std(case['dac'])),
                             dac_pp_counts=int(np.ptp(case['dac'])),
                             dac_rms_fraction_full_span=float(np.std(case['dac'])/65536),
                             rail_fraction=float(np.mean((case['dac'] == -32768) | (case['dac'] == 32767))))
    output = args.capture.with_name(args.capture.stem+'_phase_error')
    output.with_suffix('.json').write_text(json.dumps(result, indent=2)+'\n')
    columns = np.column_stack((time_s, time_s+18/ERROR_RATE_HZ, phase_only['i'], phase_only['q'],
                               good.astype(int), phase_only['phase'], phase_only['frequency'],
                               phase_only['dac'], capture_on['dac']))
    np.savetxt(output.with_suffix('.csv'), columns, delimiter=',', comments='',
               header='adc_word_time_s,dac_register_time_s,i_adc_counts,q_adc_counts,phase_valid,'
                      'phase_error_rad,frequency_error_hz,dac_phase_only_counts,dac_capture_on_counts')
    print(json.dumps(result, indent=2))

    fig, axes = plt.subplots(3, 1, figsize=(11, 10), constrained_layout=True, sharex=True)
    axes[0].plot(time_s*1e6, phase_only['i'], lw=0.65, label='I')
    axes[0].plot(time_s*1e6, phase_only['q'], lw=0.65, label='Q')
    axes[0].set(ylabel='Post-mixer ADC counts', title='RTL mixer + FIR: reconstructed I/Q')
    axes[0].legend(loc='upper right')
    for ax, case, title in ((axes[1], phase_only, 'Capture OFF'),
                             (axes[2], capture_on, f'Capture ON, weight {capture_gain}')):
        ax.plot(time_s*1e6, case['dac']/32768, lw=0.65)
        ax.set(ylabel='DAC code / 32768', ylim=(-1.08, 1.08), title=title+' — validity gating and clipping included')
        ax.axhline(1, color='gray', ls=':', lw=0.6)
        ax.axhline(-1, color='gray', ls=':', lw=0.6)
    if gain == 1:
        sign = -1 if args.control & 4 else 1
        phase_axis = axes[1].secondary_yaxis('right', functions=(lambda x: sign*np.pi*x,
                                                                 lambda x: sign*x/np.pi))
        phase_axis.set_ylabel('Phase error (rad), when valid')
        phase_axis.set_yticks([-np.pi, 0, np.pi], labels=['−π', '0', '+π'])
    axes[2].set_xlabel('Captured ADC word time (µs); DAC register follows by 73.24 ns')
    for ax in axes:
        ax.grid(alpha=0.25)
    fig.suptitle(f'{args.capture.stem}: reference {reference_hz/1e6:g} MHz, overall gain {gain}, threshold {threshold}\n'
                 'Assumed NCO phase zero at capture start; full DAC span = −1 to +1; no analog filtering', fontsize=12)
    fig.savefig(output.with_suffix('.png'), dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(11, 7), constrained_layout=True)
    psd_dbfs_hz = 10*np.log10(np.maximum(density/(32768**2/2), 1e-30))
    for ax in axes:
        ax.plot(frequency/1e6, psd_dbfs_hz, lw=0.7)
        ax.axvline(reference_hz/1e6, color='tab:red', ls='--', lw=0.8, label='Assumed reference')
        ax.set(xlabel='RF frequency (MHz)', ylabel='ADC PSD (dBFS/Hz)')
        ax.grid(alpha=0.25)
        ax.legend()
    axes[0].set(xlim=(0, ADC_RATE_HZ/2e6), title=f'{args.capture.stem}: full ADC spectrum (Hann window)')
    axes[1].set(xlim=(max(0, reference_hz/1e6-110), min(ADC_RATE_HZ/2e6, reference_hz/1e6+110)),
                title='Zoom around the PLL reference; frequency bins are 120 kHz apart')
    fig.savefig(output.with_name(args.capture.stem+'_spectrum.png'), dpi=150)
    plt.close(fig)


if __name__ == '__main__':
    main()
