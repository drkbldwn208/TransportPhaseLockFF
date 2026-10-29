"""Offline only: fixed-point piecewise-linear LUT error/resource tradeoffs.

Does not generate hardware or change any existing calibration/controller file.
Interpolation stores rounded uint16 endpoints as (base, endpoint difference),
then computes base + round(delta * fractional_address / power_of_two_stride).
"""
from pathlib import Path
import json
import math
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
POWER_PER_CODE_MW = 200 / 65536
A_EFF_MW = 184.0  # Conditional optical scale, not independently measured input power.
model = json.loads((OUT / 'aom_model.json').read_text())
ALPHA = model['alpha_rad_per_code']
UMIN = model['measured_command_range_codes'][0]
UMAX = 21335
FMAX_INDEX = int(np.floor(np.sin(ALPHA * UMAX)**2 * 65536))


def lerp_integer(x, stride, node_values, origin=0):
    """Nonnegative integer inputs; ties round upward, like a simple RTL shifter."""
    position = np.asarray(x, dtype=np.int64) - origin
    index, remainder = np.divmod(position, stride)
    base = node_values[index]
    delta = node_values[index + 1] - base
    return base + (delta * remainder + stride//2) // stride


def sensor_nodes(x, adc, power, boundary_tangent):
    values = np.interp(x, adc, power)
    if boundary_tangent:
        # Guard endpoints only: evaluation still excludes uncalibrated ADCs.
        lo, hi = x < adc[0], x > adc[-1]
        values[lo] = power[0] + (x[lo]-adc[0])*(power[1]-power[0])/(adc[1]-adc[0])
        last_guard_x = x[np.searchsorted(x, adc[-1])]
        values[hi] = power[-1] + (np.minimum(x[hi], last_guard_x)-adc[-1])*(power[-1]-power[-2])/(adc[-1]-adc[-2])
    return np.rint(values / POWER_PER_CODE_MW).astype(np.int64)


sensor_results = []
for mode in ('low_power', 'high_power'):
    table = json.loads((OUT / f'sensor_{mode}.json').read_text())
    adc, power = np.array(table['adc_counts']), np.array(table['optical_power'])
    x = np.arange(math.ceil(adc[0]), math.floor(adc[-1])+1)
    exact = np.interp(x, adc, power)
    dense = np.rint(exact / POWER_PER_CODE_MW)
    knots = np.isin(x, adc.astype(int))
    for intervals in (256, 512, 1024):
        stride = 16384 // intervals
        for boundary_tangent in (False, True):
            nodes = sensor_nodes(np.arange(0, 16384+stride, stride), adc, power, boundary_tangent)
            values = lerp_integer(x, stride, nodes)
            errors = values * POWER_PER_CODE_MW - exact
            row = dict(mode=mode, intervals=intervals, stride_adc_counts=stride,
                       boundary_guard='linear_tangent' if boundary_tangent else 'clamped_endpoint',
                       maximum_error_mW=float(max(abs(errors))), rms_error_mW=float(np.sqrt(np.mean(errors**2))),
                       maximum_relative_error_percent=float(max(abs(errors)/exact)*100),
                       maximum_error_power_codes_vs_dense=int(max(abs(values-dense))),
                       maximum_calibration_knot_error_mW=float(max(abs(errors[knots]))),
                       worst_adc_count=int(x[np.argmax(abs(errors))]),
                       all_nodes_fit_unsigned16=bool(nodes.min() >= 0 and nodes.max() <= 65535),
                       bram36_both_sensor_banks_estimate=math.ceil(2*intervals/1024))
            sensor_results.append(row)


def inverse(index):
    return np.arcsin(np.sqrt(np.asarray(index)/65536)) / ALPHA


index = np.arange(FMAX_INDEX+1)
exact_u = inverse(index)
dense_u = np.minimum(np.rint(exact_u), UMAX).astype(np.int64)
output_results = []
for intervals, prefix in [(n, 0) for n in (512, 1024, 2048, 4096)] + [(2048, 256), (1024, 256)]:
    stride = 65536 // intervals
    nodes_x = np.arange(prefix, 65536+stride, stride)
    # Use un-clipped end nodes, then clamp the interpolated output. Otherwise
    # the last valid interpolation cell bends prematurely toward the drive cap.
    nodes = np.rint(inverse(nodes_x)).astype(np.int64)
    values = np.empty_like(index)
    low = index < prefix
    values[low] = dense_u[low]
    values[~low] = np.minimum(lerp_integer(index[~low], stride, nodes, prefix), UMAX)
    values[0] = 0
    for region, lo in [('all_programmable_including_unmeasured_dark_end', 0),
                       ('measured_command_range', UMIN), ('command_at_least4000', 4000)]:
        valid = exact_u >= lo
        error = values[valid]-exact_u[valid]
        optical_error = A_EFF_MW*(np.sin(ALPHA*values[valid])**2-index[valid]/65536)
        row = dict(intervals=intervals, stride_fraction_codes=stride, dense_prefix_entries=prefix,
                   region=region, minimum_model_command_codes=lo,
                   maximum_error_dac_codes=float(max(abs(error))), rms_error_dac_codes=float(np.sqrt(np.mean(error**2))),
                   maximum_error_dac_codes_vs_dense=int(max(abs(values[valid]-dense_u[valid]))),
                   maximum_error_mW_at_A184=float(max(abs(optical_error))),
                   rms_error_mW_at_A184=float(np.sqrt(np.mean(optical_error**2))),
                   worst_fraction_index=int(index[valid][np.argmax(abs(error))]),
                   bram36_tail_estimate=math.ceil(((65536-prefix)//stride)/1024),
                   bram36_total_if_prefix_separate=math.ceil(((65536-prefix)//stride)/1024)+(1 if prefix else 0),
                   lut6_prefix_estimate=prefix*16//64)
        output_results.append(row)

pd.DataFrame(sensor_results).to_csv(OUT/'lut_tradeoff_sensors.csv', index=False)
pd.DataFrame(output_results).to_csv(OUT/'lut_tradeoff_output.csv', index=False)
summary = dict(assumptions=dict(power_full_scale_mW=200, power_code_mW=POWER_PER_CODE_MW,
                               effective_power_mW_for_output_errors=A_EFF_MW,
                               sensor_integer_ADC_domain=[0, 16383], output_fraction_denominator=65536,
                               maximum_fraction_index=FMAX_INDEX, current_logical_memory_KiB=192,
                               current_bram36=48, device_bram36=1080,
                               interpolation='rounded endpoints; delta*x product; round-half-up right shift; final actuator clamp',
                               estimate='Resource and latency figures are architectural estimates, not synthesis or implementation results'),
               sensor_comparisons=sensor_results, output_comparisons=output_results,
               hardware_estimate=dict(sensor_interpolation_dsp48=1, output_interpolation_dsp48=1,
                                      added_registered_clocks_total=[2, 4], added_delay_ns_total=[8.1380208333,16.2760416667],
                                      explanation='Each of two lookup stages adds approximately1-2 registered interpolation clocks beyond its direct synchronous lookup; base+delta fit a32-bit word. Timing/resource mapping must be synthesized.'))
(OUT/'lut_tradeoff.json').write_text(json.dumps(summary, indent=2)+'\n')
print(pd.DataFrame(sensor_results).to_string(index=False))
print(pd.DataFrame(output_results).to_string(index=False))
