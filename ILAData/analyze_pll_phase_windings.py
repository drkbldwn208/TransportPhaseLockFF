"""Separate persistent beat-phase winding from jitter around a local phase.

Uses the image-rejected, full-rate phase from compare_pll_fpga_iq.py. A 100 us
scalar-phase average locates integer turns. For conditional steady-state
statistics, omit 200 us around each turn transition and 100 us at record ends.
Only integer turns and a constant circular-mean phase are subtracted; fast
phase excursions are retained. These are input-beat windings, not necessarily
full cycles of the ADF4108's divided PFD input, nor an atomic heating metric.
"""
import json
import numpy as np
from scipy.ndimage import uniform_filter1d
import matplotlib.pyplot as plt
from compare_pll_fpga_iq import load_record, FS_HZ, OUTPUT, save_plot


def analyze(record):
    phase = record["phase"]
    center_rad = np.angle(np.mean(np.exp(1j*phase)))
    average_samples = round(100e-6*FS_HZ)
    slow = uniform_filter1d(phase, average_samples, mode="nearest")
    turns = np.rint((slow-center_rad)/(2*np.pi)).astype(int)
    crossings = np.flatnonzero(np.diff(turns))+1
    keep = np.ones(len(phase), dtype=bool)
    keep[:average_samples] = keep[-average_samples:] = False
    for index in crossings:
        keep[max(0, index-2*average_samples):min(len(phase), index+2*average_samples)] = False
    residual = phase-2*np.pi*turns-center_rad
    slow_residual = slow-2*np.pi*turns-center_rad
    # Verify image rejection has not created or removed integer winding.
    raw_phase = np.unwrap(np.angle(record["z"]))*(-1 if record["kind"] == "PLL" else 1)
    difference = raw_phase[4096:-4096]-phase
    difference -= np.median(difference)
    winding_disagreement = np.rint(difference/(2*np.pi)).astype(int)
    assert not np.any(winding_disagreement)
    summary = dict(record=record["number"], samples=len(phase), duration_s=len(phase)/FS_HZ,
        state_changes=len(crossings), first_to_last_integer_turn_change=int(turns[-1]-turns[0]),
        retained_fraction=float(keep.mean()), residual_rms_rad=float(np.sqrt(np.mean(residual[keep]**2))),
        residual_std_rad=float(residual[keep].std()),
        slow_100us_rms_rad=float(np.sqrt(np.mean(slow_residual[keep]**2))),
        coherent_fraction=float(abs(np.mean(np.exp(1j*phase)))**2),
        image_rejection_winding_disagreement=bool(np.any(winding_disagreement)))
    return dict(record=record, summary=summary, turns=turns, slow=slow,
                residual=residual, slow_residual=slow_residual, keep=keep)


def main():
    groups = {}
    for kind in ("FPGA", "PLL"):
        records = [load_record(kind, number) for number in range(10)]
        groups[kind] = [analyze(r) for r in records if r["summary"]["reliable_unwrap"]]
    report = dict(records={kind: [r["summary"] for r in rows] for kind, rows in groups.items()},
        method="100 us scalar phase mean identifies turns; exclude +/-200 us around changes; no linear drift removal",
        limitations=["PLL record 1 omitted because unwrapping is ambiguous.",
            "Persistent input-beat winding is not necessarily a cycle slip at the divided PFD.",
            "Counts describe these short records, not a stationary long-term slip rate.",
            "Phase is measured relative to the electronic reference; the laser responsible is unidentified.",
            "Only fluctuations are calibrated; an absolute optical phase setpoint is not recorded."])
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), layout="constrained")
    for col, (kind, number, center_s) in enumerate((("PLL", 2, .00813), ("FPGA", 3, None))):
        r = next(r for r in groups[kind] if r["record"]["number"] == number)
        p = r["record"]["phase"]
        t_s = (np.arange(len(p))+4096)/FS_HZ
        if center_s is None:
            center_s = t_s[np.argmax(abs(p))]
        baseline = p[(t_s > center_s-.0007) & (t_s < center_s-.0004)].mean()
        use = abs(t_s-center_s) < .0007
        axes[0, col].plot((t_s[use]-center_s)*1e3, (p[use]-baseline)/(2*np.pi), lw=.4, alpha=.35,
                          color="#c45324" if kind == "PLL" else "#1769aa", label="Resolved phase")
        axes[0, col].plot((t_s[use]-center_s)*1e3, (r["slow"][use]-baseline)/(2*np.pi), color="black", lw=1.5,
                          label="100 µs phase average")
        axes[0, col].set(xlabel="Time from event (ms)", ylabel="Phase relative to preceding mean (turns)",
                        title=f"{kind} record {number}: " + ("persistent +1 turn" if kind == "PLL" else "large returning excursion"))
        axes[0, col].legend(fontsize=8)
    for kind, color in (("FPGA", "#1769aa"), ("PLL", "#c45324")):
        rows = groups[kind]
        errors = np.concatenate([r["residual"][r["keep"]] for r in rows])
        slow_errors = np.concatenate([r["slow_residual"][r["keep"]] for r in rows])
        summary = dict(total_resolved_duration_s=sum(r["summary"]["duration_s"] for r in rows),
                       captures_with_state_changes=sum(r["summary"]["state_changes"] > 0 for r in rows),
                       conditional_phase_rms_rad=float(np.sqrt(np.mean(errors**2))),
                       conditional_slow_100us_rms_rad=float(np.sqrt(np.mean(slow_errors**2))),
                       conditional_central_95_percent_rad=np.percentile(errors, [2.5, 97.5]).tolist())
        report[kind] = summary
        axes[1, 0].hist(errors, bins=np.linspace(-6, 6, 151), density=True, histtype="step", lw=1.5, color=color,
                        label=f"{kind}: {summary['conditional_phase_rms_rad']:.2f} rad RMS")
        axes[1, 1].hist(slow_errors, bins=np.linspace(-2, 2, 151), density=True, histtype="step", lw=1.5, color=color,
                        label=f"{kind}: {summary['conditional_slow_100us_rms_rad']:.2f} rad RMS")
    axes[1, 0].set(xlabel="Phase about local integer-turn plateau (rad)", ylabel="Probability density (1/rad)",
                   title="Between transitions: PLL has slightly smaller total jitter")
    axes[1, 1].set(xlabel="100 µs averaged phase error (rad)", ylabel="Probability density (1/rad)",
                   title="FPGA has a much quieter slowly varying phase")
    for ax in axes[1]:
        ax.legend(fontsize=8)
    for ax in axes.flat:
        ax.grid(alpha=.2)
    fig.suptitle("Persistent beat-phase winding and steady-state jitter are different measures")
    fig.supxlabel("Same 2 MHz offline image rejection for both datasets; no extra complex decimation.\n"
                  "Lower panels omit ±200 µs around winding transitions and subtract integer turns only. Different capture conditions.", fontsize=9)
    save_plot(fig, "pll_fpga_phase_windings")
    (OUTPUT/"pll_fpga_phase_windings.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({key: report[key] for key in ("PLL", "FPGA")}, indent=2))


if __name__ == "__main__":
    main()
