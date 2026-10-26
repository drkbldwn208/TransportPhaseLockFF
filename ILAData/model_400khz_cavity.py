"""Drive a fixed, resonant 400 kHz-FWHM cavity with the measured phase.

Physical model: da/dt = pi*linewidth_hz * (exp(i*phi(t)) - a). a=1 for
a monochromatic resonant input of unit amplitude. No small-phase expansion.
Assume all measured beat phase belongs to the pump, a quiet reference,
constant input power, and no cavity-length servo, atomic backaction or motion.
Reuse identical 2 MHz image rejection for both capture batches. The optical
input is exp(i*phi), so adding integer turns cannot create permanent error.
"""
import json
import numpy as np
from scipy.signal import lfilter
from scipy.ndimage import maximum_filter1d, minimum_filter1d
from compare_pll_fpga_iq import load_record, FS_HZ, OUTPUT, save_plot
import matplotlib.pyplot as plt

LINEWIDTH_HZ = 400e3  # Intensity FWHM, confirmed by the user.
FIELD_RATE_PER_S = np.pi*LINEWIDTH_HZ
GUARD = 1024


def cavity_field(input_field, sample_rate_hz=FS_HZ):
    """Exact recurrence for an input field linear between sampled endpoints.

    This avoids assigning a full sample of artificial delay. Initial cavity
    field equals the first input value; exclude a guard much longer than tau.
    """
    step = FIELD_RATE_PER_S/sample_rate_hz
    decay = np.exp(-step)
    ratio = -np.expm1(-step)/step
    b0, b1 = 1-ratio, ratio-decay
    field, _ = lfilter([b0, b1], [1, -decay], input_field, zi=[ratio*input_field[0]])
    return field


def fastest_turn(phase_rad):
    """Smallest sampled interval containing a 2pi excursion, not a slip count.

    The phase may return immediately afterward. A rolling range prevents
    missing a short excursion merely because it returns by a chosen end time.
    """
    lo, hi = 1, 1024
    while hi-lo > 1:
        length = (lo+hi)//2
        span = maximum_filter1d(phase_rad, length)-minimum_filter1d(phase_rad, length)
        if span.max() >= 2*np.pi:
            hi = length
        else:
            lo = length
    span = maximum_filter1d(phase_rad, hi)-minimum_filter1d(phase_rad, hi)
    index = int(np.argmax(span))
    return dict(minimum_interval_s=(hi-1)/FS_HZ, center_index=index,
                center_in_original_capture_s=(index+4096)/FS_HZ)


def analyze_record(kind, number):
    record = load_record(kind, number)
    if not record["summary"]["reliable_unwrap"]:
        return None
    phase = record["phase"]
    pump = np.exp(1j*phase)
    field = cavity_field(pump)
    assert np.max(abs(field)) <= 1+1e-12  # Passive low-pass of unit input.
    interior = slice(GUARD, -GUARD)
    power = abs(field[interior])**2
    lag = np.angle(field[interior]*pump[interior].conj())
    interval_samples = round(FS_HZ/FIELD_RATE_PER_S)
    increments = phase[interval_samples:]-phase[:-interval_samples]
    # Count all phase ranges inside a lifetime, not just endpoint changes.
    lifetime_ranges = (maximum_filter1d(phase, interval_samples+1)
                       - minimum_filter1d(phase, interval_samples+1))
    summary = dict(record=number, kind=kind,
        phase_increment_interval_s=interval_samples/FS_HZ,
        phase_increment_rms_rad=float(np.sqrt(np.mean(increments**2))),
        maximum_phase_range_within_lifetime_rad=float(max(lifetime_ranges)),
        fastest_two_pi_excursion=fastest_turn(phase),
        mean_cavity_power_relative_to_ideal=float(power.mean()),
        power_std_relative_to_mean=float(power.std()/power.mean()),
        power_percentiles_1_5_50_95_99=np.percentile(power, [1, 5, 50, 95, 99]).tolist(),
        cavity_minus_pump_phase_rms_rad=float(np.sqrt(np.mean(lag**2))))
    return dict(summary=summary, phase=phase, pump=pump, field=field, record=record)


def checks(example):
    # DC, detuned monochromatic response, and spectral/time-domain agreement.
    assert np.allclose(cavity_field(np.ones(4096)), 1, atol=1e-12)
    t_s = np.arange(32768)/FS_HZ
    tone_hz = 100e3
    tone = np.exp(2j*np.pi*tone_hz*t_s)
    measured_gain = np.mean(cavity_field(tone)[GUARD:]/tone[GUARD:])
    expected_gain = 1/(1+2j*tone_hz/LINEWIDTH_HZ)
    assert abs(measured_gain/expected_gain-1) < 2e-4
    pump, field, phase = example["pump"], example["field"], example["phase"]
    f_hz = np.fft.fftfreq(len(pump), 1/FS_HZ)
    spectral_mean_power = np.sum(abs(np.fft.fft(pump))**2/(1+(2*f_hz/LINEWIDTH_HZ)**2))/len(pump)**2
    time_mean_power = np.mean(abs(field[GUARD:-GUARD])**2)
    assert abs(spectral_mean_power-time_mean_power) < .002
    # Halve the timestep, interpolating phase then reconstructing the field.
    fine_phase = np.interp(np.arange(2*len(phase)-1)/2, np.arange(len(phase)), phase)
    fine_field = cavity_field(np.exp(1j*fine_phase), 2*FS_HZ)[::2]
    interior = slice(GUARD, -GUARD)
    relative_error = np.sqrt(np.mean(abs(field[interior]-fine_field[interior])**2)
                             / np.mean(abs(fine_field[interior])**2))
    assert relative_error < .002
    return dict(tone_relative_error=float(abs(measured_gain/expected_gain-1)),
                spectral_mean_power=float(spectral_mean_power), time_mean_power=float(time_mean_power),
                timestep_halving_field_relative_rms_error=float(relative_error))


def main():
    groups = {kind: [r for n in range(10) if (r := analyze_record(kind, n)) is not None]
              for kind in ("PLL", "FPGA")}
    report = dict(intensity_fwhm_hz=LINEWIDTH_HZ, field_corner_hz=LINEWIDTH_HZ/2,
        field_lifetime_s=1/FIELD_RATE_PER_S, energy_lifetime_s=1/(2*FIELD_RATE_PER_S),
        equation="da/dt = pi * FWHM_Hz * (exp(i*phi(t)) - a)",
        assumptions=["All measured beat phase is pump noise; reference assumed quiet.",
            "Constant optical input amplitude; RF beat AM is intentionally excluded.",
            "Fixed cavity resonance at mean pump frequency; no servo, motion or atomic backaction.",
            "PLL record 1 excluded because its unwrapped phase is ambiguous.",
            "Same 2 MHz offline image rejection; finite capture bandwidth and duration.",
            "Results predict the simple cavity model, not a measured cavity transmission."],
        records={kind: [r["summary"] for r in rows] for kind, rows in groups.items()}, checks={})
    for kind, rows in groups.items():
        keys = ("mean_cavity_power_relative_to_ideal", "power_std_relative_to_mean", "cavity_minus_pump_phase_rms_rad")
        report[kind] = {key: dict(mean=float(np.mean([r["summary"][key] for r in rows])),
                                 minimum=float(min(r["summary"][key] for r in rows)),
                                 maximum=float(max(r["summary"][key] for r in rows))) for key in keys}
        report[kind]["phase_increment_rms_rad"] = float(np.sqrt(np.mean([r["summary"]["phase_increment_rms_rad"]**2 for r in rows])))
        report["checks"][kind] = checks(rows[0])

    fig, axes = plt.subplots(3, 2, figsize=(12, 9), layout="constrained")
    for col, (kind, number) in enumerate((("PLL", 2), ("FPGA", 8))):
        r = next(r for r in groups[kind] if r["summary"]["record"] == number)
        event = r["summary"]["fastest_two_pi_excursion"]
        center = event["center_index"]
        indices = np.arange(center-round(12e-6*FS_HZ), center+round(12e-6*FS_HZ))
        time_us = (indices-center)/FS_HZ*1e6
        # Compare field phases modulo 2pi. An independent unwrap of the cavity
        # can accumulate different turns when its amplitude approaches zero.
        offset = r["phase"][indices].mean()
        cavity_phase = r["phase"]+np.angle(r["field"]*r["pump"].conj())
        branch_jumps = np.r_[False, abs(np.diff(cavity_phase)) > np.pi]
        cavity_phase[branch_jumps | (abs(r["field"]) < .05)] = np.nan
        axes[0, col].plot(time_us, r["phase"][indices]-offset, label="Measured pump phase", lw=1)
        axes[0, col].plot(time_us, cavity_phase[indices]-offset, label="Cavity phase, modulo 2π nearest pump", lw=1)
        axes[0, col].set(ylabel="Phase (rad)", title=f"{kind} record {number}: 2π excursion within {event['minimum_interval_s']*1e6:.2f} µs")
        axes[1, col].plot(time_us, abs(r["field"][indices])**2, color="#268477", lw=1.3)
        axes[1, col].axhline(1, color=".5", ls=":")
        axes[1, col].set(ylabel="Cavity power / ideal resonant power", ylim=(0, 1.05),
                        title="Constant incident power; variations arise from phase dynamics")
        axes[0, col].axvspan(0, 1e6/FIELD_RATE_PER_S, color=".5", alpha=.15, label="One field lifetime")
        axes[0, col].legend(fontsize=8)
        rows = groups[kind]
        powers = np.concatenate([abs(x["field"][GUARD:-GUARD])**2 for x in rows])
        axes[2, col].hist(powers, bins=np.linspace(0, 1, 101), density=True, histtype="step", color="#268477")
        axes[2, col].set(xlabel="Cavity power / ideal resonant power", ylabel="Probability density", xlim=(0, 1),
                        title=f"All resolved {kind} captures: predicted power distribution")
        for ax in axes[:2, col]:
            ax.set(xlabel="Time from fast excursion (µs)", xlim=(-12, 12))
    for ax in axes.flat:
        ax.grid(alpha=.2)
    fig.suptitle("400 kHz intensity FWHM: field lifetime 0.796 µs, response corner 200 kHz")
    fig.supxlabel("Complex-field response, no small-phase approximation; cavity-phase branches are broken at ±π lag and near zero power.\n"
                  "Conditional prediction: quiet reference, fixed resonant cavity, constant pump power; recorded beat phase assigned to pump.", fontsize=9)
    save_plot(fig, "cavity_400khz_response")
    (OUTPUT/"cavity_400khz_response.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({key: report[key] for key in ("PLL", "FPGA", "checks")}, indent=2))


if __name__ == "__main__":
    main()
