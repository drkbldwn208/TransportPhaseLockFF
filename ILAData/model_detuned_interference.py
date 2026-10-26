"""Estimate pump-FM modulation of a transversely scattered cavity lattice.

Fixed atomic density order and polarizability; constant pump power; all beat
phase assigned to the pump. This is the first-order response in frequency
excursion / cavity detuning, NOT an expansion in total accumulated phase.
It excludes atomic motion, changes of dispersive cavity shift, optical AM,
and nonlinear frequency mixing. It is not a self-organization/heating model.

The cavity intensity FWHM is 400 kHz. Choose red effective detuning -10 MHz;
the magnitudes of these cavity-only transfer functions are unchanged for
the opposite sign. The data and their preprocessing are documented in
compare_pll_fpga_iq.py. PLL record 1 is excluded because unwrapping fails.
"""
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "10-14-IQ"
DETUNING_HZ = -10e6  # Pump minus atom-shifted cavity resonance.
HWHM_HZ = 200e3


def transfer_functions(frequency_hz, detuning_hz=DETUNING_HZ):
    """Return fractional interference depth / Hz and relative phase rad / Hz.

    In the instantaneous pump frame b obeys
    db/dt = 2*pi*(-gamma + i*(Delta + delta_nu))*b - i*S.
    At fixed real scattering source S, interference depth is proportional
    to Re(b), not abs(b)**2. Linearize this equation about its steady state.
    All frequencies below are in Hz; the factors of 2*pi cancel.
    """
    gamma_hz = HWHM_HZ
    rate_hz = gamma_hz + 1j*np.asarray(frequency_hz)
    denominator_hz2 = rate_hz**2 + detuning_hz**2
    depth_per_hz = ((gamma_hz*rate_hz - detuning_hz**2)
                    / (detuning_hz*denominator_hz2))
    phase_rad_per_hz = rate_hz/denominator_hz2
    return depth_per_hz, phase_rad_per_hz


def main():
    # Check the DC limit against a finite difference of the static response.
    delta_hz = DETUNING_HZ
    response = lambda d: d/(d*d + HWHM_HZ**2)
    dc_derivative = ((response(delta_hz+1)-response(delta_hz-1))
                     / (2*response(delta_hz)))
    assert np.isclose(transfer_functions(0)[0], dc_derivative, rtol=1e-7)
    # Well off resonance, fractional depth sensitivity tends to -1/Delta.
    assert np.isclose(transfer_functions(0)[0], -1/delta_hz, rtol=.001)

    report = dict(
        effective_cavity_detuning_hz=DETUNING_HZ,
        cavity_intensity_fwhm_hz=2*HWHM_HZ,
        input_spectra="pll_fpga_iq_spectra.npz",
        method="S_frequency(f) = f**2 * S_phase(f); first-order cavity transfer",
        assumptions=[
            "Fixed density order parameter and atomic polarizability.",
            "All measured beat phase noise belongs to pump; reference quiet.",
            "Constant pump power; fixed atom-shifted cavity resonance.",
            "No nonlinear frequency mixing or self-consistent atomic motion.",
            "RMS values cover specified bands, not the entire optical spectrum.",
            "Low-frequency estimates can miss downconversion of stronger fast noise.",
        ],
        groups={},
    )
    with np.load(OUTPUT / "pll_fpga_iq_spectra.npz") as spectra:
        for group in ("FPGA", "PLL", "PLL_quiet"):
            frequency_hz = spectra[group+"_f"]
            frequency_psd_hz2_per_hz = frequency_hz**2*spectra[group+"_phase"]
            depth, relative_phase = transfer_functions(frequency_hz)
            bin_width_hz = frequency_hz[1]-frequency_hz[0]
            rows = []
            for low_hz, high_hz in ((1e3, 1e4), (1e4, 1e5),
                                    (1e5, 1e6), (1e3, 1e6)):
                band = (frequency_hz >= low_hz) & (frequency_hz < high_hz)
                weights = frequency_psd_hz2_per_hz[band]*bin_width_hz
                rows.append(dict(
                    band_hz=[low_hz, high_hz],
                    frequency_rms_hz=float(np.sqrt(weights.sum())),
                    interference_depth_rms_fraction=float(
                        np.sqrt(np.sum(abs(depth[band])**2*weights))),
                    cavity_minus_pump_phase_rms_rad=float(
                        np.sqrt(np.sum(abs(relative_phase[band])**2*weights))),
                ))
            report["groups"][group] = rows
    (OUTPUT / "detuned_interference_response.json").write_text(
        json.dumps(report, indent=2)+"\n")
    for group, rows in report["groups"].items():
        print(group, rows[-1])


if __name__ == "__main__":
    main()
