"""Expected open-loop error waveforms; ideal model, not RTL or hardware data."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
ERROR_SAMPLE_RATE_HZ = 245.76e6
CAPTURE_GAIN = 64

def wrap_phase(phase_rad):
    return (phase_rad + np.pi) % (2 * np.pi) - np.pi

fig, axes = plt.subplots(2, 1, figsize=(9, 7), constrained_layout=True)
time_s = np.linspace(0, 25e-6, 5001)
for offset_hz, color in [(100e3, "#0072B2"), (-100e3, "#D55E00")]:
    phase_error_rad = wrap_phase(-2 * np.pi * offset_hz * time_s)
    output = phase_error_rad / np.pi
    # Break the plotted line at phase wraps, rather than drawing vertical ramps.
    output[np.r_[False, np.abs(np.diff(output)) > 1]] = np.nan
    axes[0].plot(time_s * 1e6, output, color=color,
                 label=f"Input − reference = {offset_hz / 1e3:+.0f} kHz")
axes[0].set(title="Capture off: phase error wraps once per beat period",
            xlabel="Time (µs)", ylabel="DAC error / one-sided full scale",
            ylim=(-1.1, 1.1))
axes[0].legend(loc="upper right", fontsize=9)

# At nonzero offset, phase visits the whole wrapped range. Show the output
# envelope and phase-cycle mean after clipping, at phase gain 1.
offset_hz = np.linspace(-6e6, 6e6, 2001)
phase_cycle_rad = np.linspace(-np.pi, np.pi, 4096, endpoint=False)
frequency_bias = -2 * CAPTURE_GAIN * offset_hz / ERROR_SAMPLE_RATE_HZ
output = np.clip(phase_cycle_rad[:, None] / np.pi + frequency_bias, -1, 1)
mean_output = output.mean(axis=0)
mean_output[np.abs(offset_hz) < 1] = np.nan  # No phase-cycle mean at zero offset.
axes[1].fill_between(offset_hz / 1e6, output.min(axis=0), output.max(axis=0),
                     color="#0072B2", alpha=0.18, label="Range during a phase cycle")
axes[1].plot(offset_hz / 1e6, mean_output, color="#0072B2", label="Phase-cycle mean")
for boundary_mhz in [-3.84, 3.84]:
    axes[1].axvline(boundary_mhz, color="0.5", ls=":", lw=1)
axes[1].set(title="Capture on (weight 64): saturated pulling outside ±3.84 MHz",
            xlabel="Input frequency − reference frequency (MHz)",
            ylabel="DAC error / one-sided full scale", ylim=(-1.1, 1.1))
axes[1].legend(loc="upper right", fontsize=9)
for ax in axes:
    ax.grid(alpha=0.25)
    ax.axhline(0, color="0.5", lw=0.6)
fig.suptitle("Ideal steady-tone bench expectations • phase gain 1 • default polarity", fontsize=12)
path = ROOT / "docs/laser_pll_bench_waveforms.png"
fig.savefig(path, dpi=170)
print(path)
