# R7 PLL with closed-loop and RF-chain phase FRA

This release restores the normal R7 dual-PLL architecture from the archived A7 package and adds two primary-channel phase measurements. It replaces the A8 diagnostic I/Q loopback mode. The working A8 archive and export directory are retained separately. Use the new **R7 RF-FRA** package as a matched bit/HWH/Python set; the original R7 image does not contain the RF source or phase observations.

The objective is to separate instability in the optical feedback loop from dispersion in the RF amplifier/receiver chain. Both measurements use the existing swept-sine HLS generator and two synchronous demodulators, with long coherent integration and repeated complex averaging. They do not run simultaneously. There is no random-noise source or additional filtering in the feedback path.

## Physical paths

The normal PLLs remain ADC224/3 → DAC229/1 and ADC225/1 → DAC229/3. Their NCOs, acquisition stages, 24-bit winding memories, stage-4 gain ramps, selectable IIRs, I/Q DMA monitors and legacy error/drive FRA remain available. ADC225/0 and ADC225/2 and all RFDC configuration parameters retain their prior settings. The new phase-FRA helper operates on the primary PLL only; the legacy error/drive helper remains usable for either PLL.

### Closed optical loop

Keep the normal laser wiring and lock. Inject D after the selected digital error/IIR, immediately before DAC229/1's existing formatter. Measure received phase Phi at the CORDIC output and total DAC command U. Both analog controller branches continue to receive the same output.

With negative feedback, E = −L U and U = E + D, hence:

- Received-phase response: H = Phi/D, in radians per injected DAC code.
- Full loop return ratio: L = (D−U)/U, dimensionless.
- Sensitivity: S = U/D = 1/(1+L).
- Response from output command to received phase: P = Phi/U, in rad/DAC-code. This includes the analog controller, actuator/laser and receive path but excludes digital phase-to-error scaling/IIR.

The full L includes the discriminator and selected compensator, even though Phi is observed before those stages. It also includes both physical feedback branches. No separate open-loop break is needed. A small U at high loop gain makes L sensitive to measurement error; its quality flag is separate from that for Phi/D.

The signed digital discriminator alone is E/Phi=(U−D)/Phi, in DAC codes/rad. At low frequency with IIR bypass, /160 gives approximately 65.2 codes/rad, multiplied by the tracking gain. This isolates processing after the CORDIC, including the selected IIR, from the physical return path.

The closed phase helper uses nominal commanded D. Integer sine quantization gives about 0.2% amplitude error at 32 codes for uniform generator phase coverage, with larger errors at small amplitudes and some dependence on phase-grid coverage. At very small L, cancellation in D−U magnifies this systematic error; repeat scatter does not account for it. Use a second amplitude and the legacy simultaneous E/U mode to check the high-frequency tail without nominal-D subtraction.

Legacy `laser_pll_loop_sweep` still measures E and U directly and reports L=−E/U. It uses arm word 1 and its established API. The new raw-phase measurement uses arm word 5. Do not operate both helpers concurrently.

### Open-loop RF chain

Connect DAC229/2 → amplifier chain under test → ADC224/3. Disconnect the optical controllers from the driven test setup. `setup_rf()` holds primary error DAC229/1 at DC code zero while keeping the receiver running. It programs DAC229/2's existing RFDC fine C2R mixer to 800.01 MHz and the fabric receive NCO to that same frequency. Other DAC channels and ADC RFDC settings are not changed.

The new source produces I=A cos(phi), Q=A sin(phi), repeated into seven I/Q pairs per fabric word. A is constant; phi is the swept sine. This is phase modulation, with no intended amplitude modulation. Default A=8192 and peak phi=0.05 rad; verify the actual RF power and linearity of the amplifier/ADC chain. Supported helper depths are 0.005–0.2 rad. The source's idle setting I=32767,Q=0 exactly matches the previous constant tone; reducing amplitude is an explicit test setup action.

Measure H_RF = Phi_received/Phi_applied in rad/rad. Phi_applied accompanies the actual packed RF DAC word. Thus its four-register source synthesis delay divides out, while converter, cable/amplifier and receiver mixer/FIR/CORDIC delays remain. Repeat with a direct cable and suitable attenuation, at the same carrier and comparable ADC amplitude. H_chain/H_direct then isolates the added chain and fixture differences. A fixed inversion or I/Q convention contributes a constant 180° intercept, not a delay; inspect the direct baseline before interpreting absolute sign.

H_RF and the optical Phi/D have different units and measurement boundaries; their ratio alone does not isolate the RF chain. The A8 direct/mixer tests measured amplitude-envelope response through post-FIR I/Q, whereas this R7 RF test measures phase modulation through CORDIC. A flat A8 response is strong evidence against an interface pole but does not exclude phase-specific RF effects or additive noise in a working laser loop.

The ZAD-1+ IF-port 100 mV constraint belongs to the separate A8 near-DC mixer test. This RF test drives DAC229/2 directly into an RF chain, not that IF port. No near-DC calibration is required here.

## Registers and precision

Existing PLL version is 0xA7. New dual-channel GPIO `pll_rf_source` at **0xA0300000** has:

| Offset | Meaning |
|---|---|
| 0 | Output amplitude, unsigned codes in bits 15:0, clamped at 32767; reset 32767 |
| 8 | Read-only feature ID **0x52463701** (RF7 revision 1) |

The A8 `pll_loopback_i/q` mean GPIOs are removed. All legacy R7 PLL addresses remain. The former constant-source broadcaster is removed: DAC229/0 retains its original constant source, while DAC229/2 receives the new independent PM stream. The second PLL's unused PM output is unconnected and optimized away; its readiness input is tied high.

`pll_fra` control bit 0 arms; bit 1 selects RF PM; bit 2 selects raw received phase with ordinary error-output injection. Mode is latched on arm. Valid combinations are 1 (legacy E/U), 3 (RF PM), 5 (closed raw phase). Status bits 9 and 8 report phase-observation and RF mode. Existing done/fault/envelope fields are unchanged.

CORDIC phase has 2^18 codes/turn, **23.97 microradians per code**. The diagnostic observer subtracts adjacent wrapped phases and accumulates signed differences into 20 bits relative to arm, providing approximately **±2 turns** without reducing phase precision. This is separate from the feedback's 24-bit winding counter. The phase observer rails and sets a sticky diagnostic flag if its range is exceeded. Missing valid samples invalidate a block rather than silently bridging a gap. For RF tests the equal carrier/reference frequencies avoid continuous phase drift; for optical tests the laser must remain phase locked within the observer's range.

The source quarter-wave ROM uses a 16-bit phase grid (**95.87 microradians**) and 18-bit sine/cosine values. Two amplitude products produce signed 16-bit DAC codes. The applied-phase observation follows the midpoint lookup phase; very small remaining errors come from integer I/Q amplitude rounding. Averaging does not eliminate deterministic quantization or clipping bias. Test a second modulation depth to check linearity.

## Averaging and diagnostic flags

The default notebook uses at least 1 second of coherent integration per block, 16 cycles at very low frequency, at least 50 ms settling, 8 accepted blocks and up to 24 attempts per point to target complex-response SNR 30. The hardware integrates synchronous products at 245.76 MHz; the long integration itself provides the narrowband averaging without inserting a decimator or any delay in the feedback. A one-second rectangular coherent average has order-0.5 Hz one-sided equivalent noise bandwidth per demodulated quadrature; repeat scatter captures additional noise and drift. Alternating probe polarity suppresses phase-coherent backgrounds only if they are stable across the pair.

The helper averages complex numerator/denominator phasors before division. Complex SEM is estimated from repeat residuals Phi−H D (or Phi_received−H Phi_applied), retaining their noise correlation. `reliable` requires the requested repeat count/SNR and no retained clipping. `loop_reliable` separately checks whether U is resolved well enough to divide. A stable systematic error can pass these scatter tests, so amplitude repeats and direct-cable baselines remain necessary.

Counter names are retained from the shared legacy ABI:

- `dac_clip_samples/fraction`: actual output adder clipping during integration.
- `detector_saturated_samples/fraction`: in phase modes, diagnostic phase overflow or any raw ADC lane within 16 counts of a rail; in closed mode, also the active discriminator/IIR saturation. These sources are ORed and cannot be separated from this counter alone.
- `outside_clip_samples`: events during ramp/settling, separate from the integration interval.
- `error_range_codes`, `drive_range_codes`: signed DAC-command extrema, not phase radians or RF input amplitude.

A diagnostic phase overflow can occur while a scope sees bounded output. `allow_clipping=True` retains such blocks, with explicit clipping/unreliable flags; averaging does not make nonlinear clipping unbiased. Missing phase, source/AXIS gaps, RF DAC stalls, wrong mode and changed configuration always reject the block. RF source/detector validity is checked throughout the active run. Raw ADC rails are a near-full-scale check, not a detector for amplifier compression before the ADC.

Each ADC lane's rail comparison is registered near the converter. The FRA delays its window and other clipping flags by the same clock before counting, preserving the first/last measured sample and excluding adjacent ramp/settling events. This diagnostic pipeline adds **zero feedback clocks**; RTL boundary tests check both sides of the integration window.

## Pipeline and latency

No new registers are inserted in either PLL's error feedback path. With IIR bypass, ADC word to DAC output register remains **18 clocks** for stages 0/2, **20** for stage 3, **23** for stage 4, at 245.76 MHz. The FIR's 7.884 ns signal group delay and physical RFDC/analog delays remain additional. IIR selection adds its existing 2–3 clocks plus the intended pole/zero response. These are RTL sample transport measurements, not whole-board propagation measurements.

| Path | Registers / behavior |
|---|---|
| Existing error injection | Three stimulus registers for tone/envelope alignment; combinational addition before the existing DAC register |
| New RF PM source | ROM/sign capture → signed sin/cos → two amplitude products → output/packing; four registers, RF test source only |
| New received-phase observer | One registered relative-phase update; drive and sine/cosine references delayed equally |
| ADC clipping diagnostics | One clock of lane flags, with equally delayed counting windows; outside feedback |
| Demodulation/host averaging | Observation side path; cannot stall feedback; a dropped probe record invalidates measurement |
| Mode entry/exit | Existing 4096-step sine envelope, 1.067 ms up/down; no abrupt full-amplitude stimulus switch |

The applied RF phase reference removes the source synthesis latency from H_RF. It does not remove RFDC buffering or conversion. Startup/reset may change converter alignment; repeat the direct baseline after clock/converter resets when comparing absolute delays.

For context, the uploaded Oct 13 A8 sweeps fit 189.02 ns (direct RF) and 194.28 ns (mixer fixture) over 10 kHz–1 MHz with free phase intercept; residual RMS is 0.013°/0.053°. Their gain spans are 0.141/0.123 dB over the whole sweep. These already include DAC, ADC, mixer and FIR. Adding the remaining stage-4 phase/error path suggests about 250–270 ns for those electronics with/without selected IIR, not another full 100 ns on top. A 300 ns engineering budget consumes 10.8° at 100 kHz, 18.9° at 175 kHz, 32.4° at 300 kHz and 54° at 500 kHz. Actuator/laser/filter phase remains to be measured; this budget is not the phase margin of the full loop.

## Notebook, files and verification

`laser_pll_phase_fra.ipynb` contains the user's custom clock setup, matching module refresh, selectable hardware download, wiring, one-point test, full sweep, settings capture and plots. `initialize_hardware=False` preserves an existing `ol` and its lock; True initializes clocks/tiles and downloads the matching image. Normal lock acquisition remains in `laser_pll_bringup.ipynb`. Helpers import the versioned `laser_pll_R7.py`, an exact package copy of the canonical helper, and explicitly bind both FRA modules to the same object to avoid stale-import mismatches.

Data are saved in `phase_fra_data/`: point CSV, per-block CSV, JSON conditions/settings and PNG response plots. Both success and exceptions remove the probe while preserving the feedback state or RF carrier. The RF carrier can be muted independently with `ol.pll_rf_source.write(0, 0)`.

Build with `scripts/build_laser_pll_rf_fra.tcl`, then package with `scripts/package_laser_pll_rf_fra.py`. The package directory is `build/laser_pll_R7_FRA/`, separate from A8. Its `verification.json` records routed timing, resource use, file hashes and test evidence. Actual HLS RTL simulations verify legacy E/U, closed raw-phase and RF phase transfer recovery, wrap crossings, clipping/faults and source alignment. Host/notebook models check units, a known 403 ns delay, both sweep modes, state-preserving cleanup and files. These tests do not certify an optical lock or converter hardware performance.

The October 13 implementation in Vivado 2024.1 passes the existing constraints after post-route optimization: setup **+0.002 ns**, hold **+0.010 ns**, pulse width **+0.534 ns**, with zero failing endpoints. Setup margin is tight. Existing clock/external-I/O constraint limitations remain; these numbers are not a board-level delay measurement. Full-design utilization is 80,545 LUTs, 107,402 flip-flops, 344.5 equivalent 36-kbit BRAMs and 380 DSPs. The initial ADC-to-clipping-counter timing failure was removed by registering each lane's diagnostic, without changing the feedback pipeline.

Source details, including line groups for each new module, are in [the RTL walkthrough](laser_pll_rtl_walkthrough.md). The fixed RF carrier uses the existing [AMD RFDC mixer](https://docs.amd.com/r/en-US/pg269-rf-data-converter/Mixer-Settings); time-varying phase is applied in programmable-logic I/Q, consistent with quadrature DDS phase-offset modulation ([AMD DDS implementation](https://docs.amd.com/r/en-US/pg141-dds-compiler/Implementation-Tab)). Stability must be assessed from the full return ratio at its gain crossovers ([phase-margin definition](https://www.mathworks.com/help/control/ref/dynamicsystem.margin.html)).
