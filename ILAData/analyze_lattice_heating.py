"""Estimate technical heating of a 741 nm Dy lattice from measured beat I/Q.

Physical model: a noiseless optical reference, a single isolated optical line,
constant optical intensity, and noninteracting atoms initially in the lowest
band of V(x)=s*Er*sin(k*x)**2. The mean lattice depth is an input, not inferred
from optical power. Compute initial band depletion and energy deposition,
not a trap lifetime or equilibrium temperature.

One-sided noise PSDs are per Hz. Frequency noise follows full-rate phase
unwrapping; complex I/Q is never averaged again before extracting phase.
Nonlinear detuning conversion is a quasistatic dispersive approximation.
Unknown reference/detector noise, resonant optical tails, intensity noise,
collisions, finite-envelope escape and mechanical mirror noise are excluded.
"""
from pathlib import Path
import hashlib
import json
import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/lattice_heating_mpl")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from matplotlib.ticker import ScalarFormatter
import numpy as np
from scipy.constants import atomic_mass, c, h, k as k_B
from scipy.linalg import eigh
from scipy.ndimage import gaussian_filter1d
from scipy.optimize import brentq
from scipy.signal import butter, find_peaks, sosfiltfilt, welch

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "10-13-IQ"
OUTPUT = ROOT / "lattice_heating"
MASS_KG = 162*atomic_mass
WAVELENGTH_M = 741e-9
RECOIL_HZ = h/(2*MASS_KG*WAVELENGTH_M**2)
RECOIL_K = h*RECOIL_HZ/k_B
LINEWIDTH_HZ = 2000.0  # Gamma/(2*pi), used only for a separate scattering scale.
DETUNINGS_MHZ = np.array([2., 3., 5., 7., 10., 15., 20., 30., 50.])
DEPTHS_ER = np.unique(np.r_[np.linspace(1, 20, 191), np.linspace(20, 150, 261)])
TABLE_DEPTHS_ER = (5., 10., 20., 30., 50., 65., 108.)
FREQUENCY_CUTOFF_HZ = 1e6
WELCH_SAMPLES = 32768


def read_phase(number):
    path = INPUT / f"laser_iq_FPGA_shortest_{number}.npz"
    with np.load(path, allow_pickle=False) as data:
        z = data["i_adc_counts"]+1j*data["q_adc_counts"]
        sample_rate_hz = float(data["sample_rate_hz"])
    phase_rad = np.unwrap(np.angle(z))
    assert np.isfinite(z).all() and min(abs(z))/np.median(abs(z)) > .85
    assert max(abs(np.diff(phase_rad))) < .6
    return phase_rad, sample_rate_hz, dict(
        source=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        sample_rate_hz=sample_rate_hz, duration_s=len(z)/sample_rate_hz)


def frequency_record(phase_rad, sample_rate_hz, cutoff_hz):
    """Low-pass AFTER unwrapping/differentiation, to limit detector-floor mixing.

    Adjacent differences average frequency over 65 ns; their sinc response is
    essentially unity at the principal 10--200 kHz motional transitions.
    Zero-phase filtering is offline only. Trim filter end effects and remove
    the record's tiny mean offset; detuning is supplied independently.
    """
    frequency_hz = np.diff(phase_rad)*sample_rate_hz/(2*np.pi)
    sos = butter(6, cutoff_hz, fs=sample_rate_hz, output="sos")
    frequency_hz = sosfiltfilt(sos, frequency_hz)[2048:-2048]
    return frequency_hz-frequency_hz.mean()


def noise_psd(values, sample_rate_hz):
    f_hz, psd = welch(values, sample_rate_hz, nperseg=WELCH_SAMPLES,
                      noverlap=WELCH_SAMPLES//2, detrend="constant")
    # 469 Hz Gaussian sigma (~1.10 kHz FWHM) reduces single-bin estimation noise.
    # It also sets the precision with which a sharp danger-zone boundary is known.
    return f_hz, gaussian_filter1d(psd, sigma=1, mode="nearest")


def fractional_depth(frequency_hz, detuning_hz):
    """Quasistatic U proportional to 1/(Delta+delta_nu), at fixed mean depth.

    detuning_hz = laser minus atom frequency: negative red, positive blue.
    Mean normalization represents re-calibrating the actual mean lattice depth.
    This cannot model resonant photon scattering or passage through resonance.
    """
    assert np.min(abs(detuning_hz+frequency_hz)) > .1*abs(detuning_hz)
    depth = detuning_hz/(detuning_hz+frequency_hz)
    return depth/depth.mean()-1


def optical_response_depth(frequency_hz, sample_rate_hz, detuning_hz):
    """Audit the quasistatic approximation with weak-excitation optical response.

    Integrating zero-mean frequency makes the phasor periodic for the FFT.
    Re(u* p) is the symmetric dispersive force coefficient, with u* meaning
    conjugate(u), and p the field filtered by the optical susceptibility.
    Used only at +/-10 MHz, beyond the sampled optical spectral interval.
    This is not a model for saturated or resonantly scattering atoms.
    """
    phase = 2*np.pi*np.cumsum(frequency_hz)/sample_rate_hz
    field = np.exp(1j*phase)
    f_hz = np.fft.fftfreq(len(field), 1/sample_rate_hz)
    susceptibility = detuning_hz/(detuning_hz+f_hz-.5j*LINEWIDTH_HZ)
    coherence = np.fft.ifft(np.fft.fft(field)*susceptibility)
    depth = np.real(field.conj()*coherence)
    return depth/depth.mean()-1


def lattice_bands(depth_er, quasimomentum=0., basis_halfwidth=15):
    """Plane waves exp(i*(2*n+q)*kx); q in [-1,1], energies in Er.

    Return the first twelve transitions out of band 0 and matrix elements for
    fractional depth noise (sin²kx) and displacement noise (sin2kx).
    """
    n = np.arange(-basis_halfwidth, basis_halfwidth+1)
    size = len(n)
    depth_operator = .5*np.eye(size)-.25*(np.eye(size, k=1)+np.eye(size, k=-1))
    displacement_operator = (np.eye(size, k=-1)-np.eye(size, k=1))/(2j)
    energy_er, states = eigh(np.diag((2*n+quasimomentum)**2)+depth_er*depth_operator)
    gaps_hz = (energy_er[1:13]-energy_er[0])*RECOIL_HZ
    depth_matrix_sq = abs(states[:, 1:13].conj().T@depth_operator@states[:, 0])**2
    displacement_matrix_sq = abs(states[:, 1:13].conj().T@displacement_operator@states[:, 0])**2
    return gaps_hz, depth_matrix_sq, displacement_matrix_sq


def transition_rates(depth_er, gaps_hz, matrix_sq, psd_frequency_hz, depth_psd):
    """One-sided PSD normalization: 2*pi²*(perturbation/h)²*S(f_gap)."""
    sampled_psd = np.interp(gaps_hz, psd_frequency_hz, depth_psd)
    return 2*np.pi**2*(depth_er*RECOIL_HZ)**2*matrix_sq*sampled_psd


def rate_summary(rates_per_s, gaps_hz):
    return dict(ground_band_depletion_per_s=float(np.sum(rates_per_s)),
        initial_energy_er_per_s=float(np.sum(rates_per_s*gaps_hz/RECOIL_HZ)),
        energy_over_kB_uK_per_s=float(np.sum(rates_per_s*gaps_hz/RECOIL_HZ)*RECOIL_K*1e6))


def save_plot(fig, name):
    for extension in ("png", "pdf"):
        fig.savefig(OUTPUT/f"{name}.{extension}", dpi=180)
    plt.close(fig)


def main():
    OUTPUT.mkdir(exist_ok=True)
    sources, frequency_psds, nonlinear_psds = [], [], []
    frequency_rms_hz = []
    response_checks = []
    cutoff_checks = {cutoff: [] for cutoff in (5e5, 2e6)}
    for number in range(10):
        phase_rad, fs_hz, source = read_phase(number)
        frequency_hz = frequency_record(phase_rad, fs_hz, FREQUENCY_CUTOFF_HZ)
        frequency_rms_hz.append(float(frequency_hz.std()))
        source["filtered_frequency_min_max_hz"] = [float(frequency_hz.min()), float(frequency_hz.max())]
        sources.append(source)
        f_hz, psd = noise_psd(frequency_hz, fs_hz)
        frequency_psds.append(psd)
        signs = []
        for sign in (-1, 1):
            signs.append([noise_psd(fractional_depth(frequency_hz, sign*detuning*1e6), fs_hz)[1]
                          for detuning in DETUNINGS_MHZ])
        nonlinear_psds.append(signs)
        # At 10 MHz, check sensitivity of nonlinear mixing to the analysis cutoff.
        for cutoff in cutoff_checks:
            nu = frequency_record(phase_rad, fs_hz, cutoff)
            cutoff_checks[cutoff].append(noise_psd(fractional_depth(nu, -10e6), fs_hz)[1])
        if number in (0, 3, 8):
            for detuning_hz in (-10e6, 10e6):
                exact_depth = optical_response_depth(frequency_hz, fs_hz, detuning_hz)
                # Discard an additional guard at both ends of the periodic FFT.
                response_f, response_psd = noise_psd(exact_depth[2048:-2048], fs_hz)
                _, static_psd = noise_psd(fractional_depth(frequency_hz, detuning_hz)[2048:-2048], fs_hz)
                for depth_er in (5., 10., 65., 108.):
                    gaps, matrix, _ = lattice_bands(depth_er)
                    exact_rate = transition_rates(depth_er, gaps, matrix, response_f, response_psd).sum()
                    static_rate = transition_rates(depth_er, gaps, matrix, response_f, static_psd).sum()
                    ratio = float(exact_rate/static_rate)
                    assert abs(ratio-1) < .02
                    response_checks.append(dict(record=number, detuning_hz=detuning_hz,
                        depth_er=depth_er, optical_response_to_quasistatic_rate_ratio=ratio))
    frequency_psds = np.asarray(frequency_psds)
    nonlinear_psds = np.asarray(nonlinear_psds)  # record, sign, detuning, frequency
    mean_frequency_psd = frequency_psds.mean(axis=0)
    mean_nonlinear_psd = nonlinear_psds.mean(axis=0)
    index_10mhz = list(DETUNINGS_MHZ).index(10.)

    # Convergence and physical normalization checks, independent of measured PSD.
    for depth_er in (5., 10., 65., 150.):
        for q in (0., .7):
            a = lattice_bands(depth_er, q)
            b = lattice_bands(depth_er, q, 22)
            assert np.allclose(a[0], b[0], rtol=1e-9)
            assert np.allclose(a[1], b[1], atol=1e-8)
    deep_depth = 10000.
    gap, matrix, _ = lattice_bands(deep_depth, basis_halfwidth=50)
    harmonic_ft_hz = 2*RECOIL_HZ*np.sqrt(deep_depth)
    exact_white_rate = 2*np.pi**2*(deep_depth*RECOIL_HZ)**2*matrix[1]
    harmonic_white_rate = np.pi**2*harmonic_ft_hz**2/4
    assert abs(exact_white_rate/harmonic_white_rate-1) < .03
    assert abs(gap[1]/(2*harmonic_ft_hz)-1) < .03

    gaps_grid, band_rates, nonlinear_grid, shaking_grid, harmonic_grid = [], [], [], [], []
    for depth_er in DEPTHS_ER:
        gaps, matrix, shaking_matrix = lattice_bands(depth_er)
        gaps_grid.append(gaps)
        rates = transition_rates(depth_er, gaps, matrix, f_hz, mean_frequency_psd/1e14)
        band_rates.append(rates)
        nonlinear_grid.append([[transition_rates(depth_er, gaps, matrix, f_hz, psd).sum()
                                for psd in sign_psds] for sign_psds in mean_nonlinear_psd])
        # Low-delay limit per L=1 metre: k*delta_x=(2*pi*L/c)*delta_nu.
        shaking_grid.append(transition_rates(depth_er, gaps, shaking_matrix, f_hz,
                                              mean_frequency_psd*(2*np.pi/c)**2).sum())
        ft = 2*RECOIL_HZ*np.sqrt(depth_er)
        harmonic_grid.append(np.pi**2*ft**2*np.interp(2*ft, f_hz, mean_frequency_psd)/1e14/4)
    gaps_grid = np.asarray(gaps_grid)
    band_rates = np.asarray(band_rates)
    nonlinear_grid = np.asarray(nonlinear_grid)
    shaking_grid, harmonic_grid = np.asarray(shaking_grid), np.asarray(harmonic_grid)

    table = []
    for depth_er in TABLE_DEPTHS_ER:
        gaps, matrix, shaking_matrix = lattice_bands(depth_er)
        linear = transition_rates(depth_er, gaps, matrix, f_hz, mean_frequency_psd/1e14)
        red_rates = transition_rates(depth_er, gaps, matrix, f_hz, mean_nonlinear_psd[0, index_10mhz])
        blue_rates = transition_rates(depth_er, gaps, matrix, f_hz, mean_nonlinear_psd[1, index_10mhz])
        record_rates = [transition_rates(depth_er, gaps, matrix, f_hz, psd[0, index_10mhz]).sum()
                        for psd in nonlinear_psds]
        shaking = transition_rates(depth_er, gaps, shaking_matrix, f_hz, mean_frequency_psd*(2*np.pi/c)**2)
        # Uniform q occupation models a localized Wannier state; not a thermal fit.
        q_rates = []
        for q in np.arange(-20, 21)*2/41:
            q_gaps, q_matrix, _ = lattice_bands(depth_er, q)
            q_rates.append(transition_rates(depth_er, q_gaps, q_matrix, f_hz,
                                            mean_nonlinear_psd[0, index_10mhz]).sum())
        cutoff_sensitivity = {str(int(cutoff)): float(transition_rates(depth_er, gaps, matrix, f_hz,
            np.mean(psds, axis=0)).sum()) for cutoff, psds in cutoff_checks.items()}
        antinode_scattering_per_s = 2*np.pi*LINEWIDTH_HZ*depth_er*RECOIL_HZ/10e6
        table.append(dict(depth_er=depth_er, gaps_hz=gaps.tolist(),
            linear_depth_noise=rate_summary(linear, gaps),
            nonlinear_red=rate_summary(red_rates, gaps),
            nonlinear_blue=rate_summary(blue_rates, gaps),
            nonlinear_red_band_rates_per_s=red_rates.tolist(),
            nonlinear_red_record_min_max_per_s=[min(record_rates), max(record_rates)],
            nonlinear_red_uniform_q_mean_per_s=float(np.mean(q_rates)),
            nonlinear_red_q_min_max_per_s=[min(q_rates), max(q_rates)],
            nonlinear_red_analysis_cutoff_check_per_s=cutoff_sensitivity,
            geometric_shaking_per_mirror_distance_m_squared=rate_summary(shaking, gaps),
            isolated_line_antinode_scattering_per_s=antinode_scattering_per_s,
            isolated_line_standing_wave_recoil_er_per_s=antinode_scattering_per_s))

    # Locate crossings of selected measured features; matrix strengths decide risk.
    crossings = []
    for noise_peak_hz in (65000., 86000., 100000., 175000.):
        for band in (2, 4, 6):
            difference = gaps_grid[:, band-1]-noise_peak_hz
            indices = np.flatnonzero(difference[:-1]*difference[1:] < 0)
            for index in indices:
                depth = brentq(lambda s: lattice_bands(s)[0][band-1]-noise_peak_hz,
                               DEPTHS_ER[index], DEPTHS_ER[index+1])
                crossings.append(dict(noise_peak_hz=noise_peak_hz, final_band=band, depth_er=depth))
    rate_10mhz = nonlinear_grid[:, 0, index_10mhz]
    maxima, _ = find_peaks(rate_10mhz, prominence=.3)
    peaks = sorted([dict(depth_er=float(DEPTHS_ER[i]), rate_per_s=float(rate_10mhz[i]))
                    for i in maxima], key=lambda row: -row["rate_per_s"])

    fig, axes = plt.subplots(2, 2, figsize=(12, 9), layout="constrained")
    ax = axes[0, 0]
    low, high = np.percentile(frequency_psds, (10, 90), axis=0)
    ax.fill_between(f_hz/1e3, low, high, alpha=.25, label="10–90% record spread")
    ax.plot(f_hz/1e3, mean_frequency_psd, lw=1, label="Mean of ten records")
    ax.set(xscale="log", yscale="log", xlim=(2, 300), ylim=(1, 3e6),
           xlabel="Fourier frequency (kHz)", ylabel="Frequency PSD (Hz²/Hz)",
           title="Measured frequency noise; ideal reference assumed")
    ax.legend(fontsize=8)
    ax = axes[0, 1]
    for band in (2, 4, 6):
        ax.plot(DEPTHS_ER, gaps_grid[:, band-1]/1e3, label=f"0 → {band}")
    for frequency in (65, 86, 100):
        ax.axhline(frequency, color=".4", lw=.7, ls="--")
        ax.text(2, frequency+1, f"{frequency} kHz", fontsize=8)
    ax.set(xlim=(1, 150), ylim=(0, 200), xlabel="Lattice depth (Er)",
           ylabel="Transition frequency (kHz)", title="Actual q=0 band gaps, not harmonic estimates")
    ax.legend(fontsize=8)
    ax = axes[1, 0]
    ax.semilogy(DEPTHS_ER, band_rates.sum(axis=1), label="Full bands, linear detuning conversion")
    ax.semilogy(DEPTHS_ER, rate_10mhz, label="Full bands, nonlinear red detuning")
    ax.semilogy(DEPTHS_ER, harmonic_grid, "--", label="Harmonic ground-state excitation ΓE/4")
    ax.semilogy(DEPTHS_ER, shaking_grid, ":", label="Additional shaking, mirror distance 1 m")
    ax.set(xlim=(1, 150), ylim=(1e-6, 100), xlabel="Lattice depth (Er)",
           ylabel="Initial ground-band depletion (1/s)", title="10 MHz detuning; atoms initially at q=0")
    ax.axvspan(5, 10, color=".7", alpha=.2)
    ax.legend(fontsize=8, loc="lower right")
    ax = axes[1, 1]
    for band in (2, 4, 6):
        ax.semilogy(DEPTHS_ER, band_rates[:, band-1], label=f"0 → {band}")
    ax.set(xlim=(1, 40), ylim=(1e-8, 10), xlabel="Lattice depth (Er)",
           ylabel="Transition rate (1/s)", title="Higher bands contribute even in shallow lattices")
    ax.axvspan(5, 10, color=".7", alpha=.2)
    ax.legend(fontsize=8)
    for ax in axes.flat:
        ax.grid(alpha=.2)
    fig.suptitle("Predicted lattice excitation from the measured 8×-gain laser frequency noise")
    fig.supxlabel("162Dy, 741 nm, single particle, one lattice axis, measured mean depth; no photon scattering or intensity noise included.\n"
                  "Noise PSD smoothed to ~1.1 kHz FWHM. Rates describe initial excitation, not atom-loss lifetimes.", fontsize=9)
    save_plot(fig, "bands_and_rates")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.2), layout="constrained")
    # Interpolate logarithms for a readable map; only the nine detunings above
    # were evaluated. Do not imply new measurements at intermediate settings.
    display_detuning_mhz = np.geomspace(2, 50, 180)
    display_rates = np.array([np.exp(np.interp(np.log(display_detuning_mhz),
                             np.log(DETUNINGS_MHZ), np.log(row)))
                             for row in nonlinear_grid[:, 0, :]])
    for ax, xmax, vmin in zip(axes, (150, 15), (1e-5, 1e-5)):
        mesh = ax.pcolormesh(DEPTHS_ER, display_detuning_mhz, display_rates.T,
                             shading="auto", norm=LogNorm(vmin=vmin, vmax=100), cmap="magma")
        cs = ax.contour(DEPTHS_ER, display_detuning_mhz, display_rates.T,
                        levels=[.001, .01, .1, 1, 10], colors="cyan", linewidths=.65)
        ax.clabel(cs, fmt="%g /s", fontsize=8)
        ax.axhspan(2, 5, facecolor="none", hatch="///", edgecolor=".7", linewidth=0)
        ax.set(xlim=(1, xmax), ylim=(2, 50), yscale="log", xlabel="Lattice depth (Er)",
               ylabel="Magnitude of red detuning (MHz)")
        ax.set_yticks([2, 5, 10, 20, 50])
        ax.yaxis.set_major_formatter(ScalarFormatter())
        ax.axvspan(5, 10, facecolor="none", edgecolor="lime", lw=1)
    axes[0].set_title("Depths crossing the servo-noise peaks")
    axes[1].set_title("Expanded view of the present shallow lattice")
    fig.colorbar(mesh, ax=axes, extend="both", label="Initial ground-band depletion from depth noise (1/s)")
    fig.suptitle("Heating risk map at fixed calibrated depth: nonlinear dispersive estimate, q=0")
    fig.supxlabel("Hatched 2–5 MHz region: near-resonant optical sidebands and non-adiabatic response require a separate check.\n"
                  "Map interpolates nine detunings. Geometric shaking, photon recoil, intensity noise and many-body heating are excluded.", fontsize=9)
    save_plot(fig, "detuning_depth_map")

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8), layout="constrained")
    for depth_er in (5, 10, 30, 65, 108):
        index = np.argmin(abs(DEPTHS_ER-depth_er))
        rate_red = nonlinear_grid[index, 0]
        line, = axes[0].loglog(DETUNINGS_MHZ, rate_red, "o-", label=f"{depth_er} Er")
        axes[0].loglog(DETUNINGS_MHZ, band_rates[index].sum()*(10/DETUNINGS_MHZ)**2,
                       "--", color=line.get_color(), alpha=.6)
    axes[0].set(xlabel="Magnitude of red detuning (MHz)", ylabel="Ground-band depletion (1/s)",
                title="Solid: nonlinear conversion; dashed: Δ⁻² prediction")
    axes[0].legend(fontsize=8)
    for depth_er in (5, 10):
        row = next(row for row in table if row["depth_er"] == depth_er)
        rates = row["nonlinear_red_band_rates_per_s"]
        axes[1].plot(np.arange(1, 13), rates, "o-", label=f"{depth_er} Er, q=0")
    axes[1].set(yscale="log", ylim=(1e-8, .1), xlim=(.5, 8.5), xticks=range(1, 9),
                xlabel="Final band index", ylabel="Excitation rate at −10 MHz (1/s)",
                title="Depth modulation selects even bands at q=0")
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.grid(alpha=.2)
    fig.supxlabel("Nonlinearity mixes frequency noise down into weak low-frequency regions.\n"
                  "For a broad quasimomentum population, average matrix-element-weighted rates over q; see numerical summary.", fontsize=9)
    save_plot(fig, "detuning_and_band_observables")

    report = dict(
        assumptions=["162Dy, 741 nm, reference laser noiseless and RF phase a faithful optical phase measurement.",
            "Initially lowest Bloch band, q=0 unless explicitly uniform q; one noninteracting lattice axis.",
            "Mean depth calibrated; isolated optical resonance, fixed intensity; detuning=laser minus atomic resonance.",
            "Quasistatic nonlinear conversion U/Umean from Delta/(Delta+delta_nu); not an optical scattering model.",
            "1 MHz offline low-pass before nonlinear conversion; 0.5 and 2 MHz sensitivity checks at -10 MHz.",
            "Mean PSD of ten independent 17 ms captures; no receiver noise-floor subtraction or response correction.",
            "2–5 MHz results provisional: optical resonant tails, response corrections, larger excursions matter.",
            "No lifetime prediction: finite envelope, interactions, collisions, occupation and recapture are unspecified."],
        recoil_hz=RECOIL_HZ, recoil_uK=RECOIL_K*1e6,
        frequency_rms_hz=frequency_rms_hz, psd_bin_hz=float(f_hz[1]-f_hz[0]),
        psd_smoothing_fwhm_hz=float(2*np.sqrt(2*np.log(2))*(f_hz[1]-f_hz[0])),
        harmonic_white_noise_normalization_ratio=float(exact_white_rate/harmonic_white_rate),
        optical_response_checks=response_checks,
        sources=sources, table_at_10mhz=table,
        nominal_noise_peak_band_crossings=crossings,
        strongest_rate_maxima_at_minus_10mhz=peaks[:12],
        references=["https://jet.physics.ncsu.edu/publications/pdf/LaserNoise.pdf",
            "https://doi.org/10.1103/PhysRevA.58.3914",
            "https://doi.org/10.1364/OE.25.003411", "https://arxiv.org/abs/physics/9902072",
            "https://arxiv.org/abs/1002.5018", "https://arxiv.org/abs/1301.2803"])
    (OUTPUT/"heating_summary.json").write_text(json.dumps(report, indent=2)+"\n")
    np.savez_compressed(OUTPUT/"heating_arrays.npz", frequency_hz=f_hz,
        mean_frequency_psd_hz2_per_hz=mean_frequency_psd,
        frequency_psd_each_record_hz2_per_hz=frequency_psds,
        detuning_magnitude_mhz=DETUNINGS_MHZ, depth_er=DEPTHS_ER, gaps_hz=gaps_grid,
        linear_band_rates_at_10mhz_per_s=band_rates,
        nonlinear_red_ground_band_rates_per_s=nonlinear_grid[:, 0],
        nonlinear_blue_ground_band_rates_per_s=nonlinear_grid[:, 1],
        shaking_ground_band_rates_per_s_per_m2=shaking_grid)
    print(json.dumps(dict(recoil_hz=RECOIL_HZ, table=table,
                          crossings=crossings, strongest_rate_peaks=peaks[:8]), indent=2))


if __name__ == "__main__":
    main()
