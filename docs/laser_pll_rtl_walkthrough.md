# Laser PLL RTL walkthrough
This is a source-line guide to every synthesizable handwritten PLL module. Adjacent lines forming one statement or pipeline operation are grouped. Blank lines and closing braces have no independent hardware behavior. Line numbers refer to this revision; pipeline timing and GPIO units are in [laser_pll.md](laser_pll.md).
`wire`/continuous assignments describe combinational hardware; `reg` values assigned on a rising edge describe stored state. Nonblocking assignments read the previous register values on that edge. A `for (genvar ...)` creates parallel hardware, whereas the FFT state machine deliberately reuses a serial datapath. All clocks here are 245.76 MHz. The A7 IIR advances its recurrence on alternate edges; its effective update rate is 122.88 MS/s.

## laser_pll.sv
[Open source](../TransportPhaseLockFF.srcs/sources_1/new/laser_pll.sv). Current R7 RF-FRA revision; the archived A8 package retains its own walkthrough.

| Source lines | What the hardware does |
|---|---|
| 1–13 | Declares clock/reset, raw ADC stream and existing error DAC stream. |
| 14–18 | New independent RF-source control, feature ID and DAC229/2 stream. |
| 19–34 | Existing PLL NCO/acquisition/tracking/IQ-monitor interfaces. |
| 35–51 | Existing IIR and HLS FRA controls, counters, tone/probe/reference interfaces. |
| 52–62 | PLL diagnostic ports and decoded enable, clear, amplitude threshold. |
| 63–70 | Continuously runs the fabric mixer/NCO and accepts all ADC data. |
| 71–77 | Runs I/Q FIRs with detector enable/reset. |
| 78–83 | Max-norm amplitude threshold gates valid phase extraction. |
| 84–89 | CORDIC measured phase and validity. |
| 91–107 | Wrapped frequency/phase detector, separate 24-bit slip memory and stage-3 scaling. |
| 108–112 | Stage-4 tracking gain and saved phase origin. |
| 113–118 | I/Q DMA monitor before CORDIC; no loop backpressure. |
| 119–124 | Independent FFT coarse estimator. |
| 125–136 | Existing acquisition stage selection and smooth handoff. |
| 137–143 | Existing selectable lead–lag IIR; bypass adds no registers. |
| 144–151 | Independent RF phase source, amplitude GPIO, feature ID and applied-phase record. |
| 152–162 | Registers each ADC lane’s near-rail comparison, then ORs flags for phase-FRA diagnostics; outside feedback. |
| 163–178 | FRA injection and observation, with raw phase and applied RF-phase inputs. |
| 179–182 | Existing error DAC formatter, validity and saturation. |
| 183–186 | Original PLL diagnostic words. |

## laser_pll_mixer.sv
[Open source](../TransportPhaseLockFF.srcs/sources_1/new/laser_pll_mixer.sv).
| Source lines | What the hardware does |
|---|---|
| 1–4 | Defines real-to-complex mixing by exp(−j reference phase); lane zero is earliest. |
| 5–10 | Clock/reset, eight raw ADC samples, valid flag and staged 48-bit frequency controls. |
| 11–16 | Eight 18-bit I/Q samples plus delayed validity, commit acknowledgment and active frequency. |
| 17–20 | Keeps the 48-bit accumulated reference phase, committed FCW and four-stage valid shift register. |
| 21–24 | Detects a change of the commit toggle. Restart is a separate explicit command. |
| 25–30 | Global reset zeros DDS phase, frequency, acknowledgment and valid history. |
| 31 | Advances the reference by eight sample-frequency increments every fabric clock, modulo one turn. |
| 32–34 | Atomically captures both staged FCW halves and acknowledges the toggle. |
| 35–36 | Optionally restarts reference phase; ordinary frequency commits do not do this. |
| 37–41 | Delays ADC validity by the mixer pipeline while the DDS continues through input gaps. |
| 43–44 | Generates eight parallel lanes and a 16-bit lookup phase register in each. |
| 45 | Adds a quarter turn to obtain cosine from the same sine table. |
| 46–47 | Reflects quadrants into quarter-wave ROM addresses; midpoint samples make reflection exact. |
| 48–50 | Offsets each lane by its chronological sample index; loads the 18-bit quarter-wave BRAM table. |
| 51–55 | Declares BRAM outputs, quadrant signs, signed sin/cos, ADC alignment registers and full products. |
| 56–58 | First pipeline edge captures the upper DDS phase bits and the lane’s ADC sample. |
| 59–63 | Second edge reads sine/cosine magnitudes, aligns their signs and advances the ADC sample. |
| 64–66 | Third edge applies quadrant signs and completes ADC alignment. |
| 67–69 | Fourth edge computes I=x*cos and Q=−x*sin; this sign makes phase equal signal minus reference. |
| 70–74 | Exports 18-bit products retaining two fractional ADC bits for the FIR. |

## laser_pll_fir.sv
[Open source](../TransportPhaseLockFF.srcs/sources_1/new/laser_pll_fir.sv).
| Source lines | What the hardware does |
|---|---|
| 1–4 | Defines a 32-tap real-coefficient FIR evaluated at the eighth sample of each word. |
| 5–11 | Receives eight signed 18-bit samples and emits one signed 24-bit filtered value plus valid. |
| 12–14 | Includes Q1.17 coefficients and allocates 24 older samples plus the current eight-sample window. |
| 15–20 | Allocates full products and a growing-width adder tree to avoid arithmetic wraparound. |
| 21–22 | Tracks four computation stages and three history words required after reset/gaps. |
| 23–25 | Orders newest-to-oldest samples so tap zero multiplies lane seven of the current word. |
| 26–28 | Registers all 32 coefficient products; one instance is used for each quadrature. |
| 29–30 | Forms combinational pair sums of registered products. |
| 31–32 | Forms combinational pair sums of the previous registered four-term sums. |
| 33–37 | Clears sample history after reset or a missing ADC word; gaps cannot form a continuous filter window. |
| 38–40 | Shifts in eight new samples and counts until all three history words exist. |
| 41–43 | Moves history-qualified validity through the four computation stages. |
| 44–45 | Registers sums of four tap products. |
| 46–47 | Registers sums of sixteen tap products. |
| 48–49 | Registers the final sum of all 32 products. |
| 50–51 | Removes eleven fractional bits: two ADC fractional bits plus 17 coefficient bits become eight. |
| 52–55 | Saturates into signed 24-bit I/Q and outputs the corresponding delayed valid flag. |

## laser_pll_cordic.sv
[Open source](../TransportPhaseLockFF.srcs/sources_1/new/laser_pll_cordic.sv).
| Source lines | What the hardware does |
|---|---|
| 1–4 | Defines grouped vectoring CORDIC atan2 with an 18-bit signed full-turn output. |
| 5–12 | Clock/reset, signed 24-bit I/Q, input validity, measured phase and output validity. |
| 13–14 | Defines the fixed elementary rotation lookup function. |
| 15–20 | Stores round(atan(2^−k)/(2π)*2^24) for iterations 0…17. |
| 21–23 | Returns zero for unused indices and closes the constant lookup function. |
| 24–27 | Allocates seven vector/angle stage boundaries and seven validity bits. |
| 28–29 | Sign-extends input vectors to 26 bits to accommodate CORDIC magnitude growth. |
| 30–34 | Rotates left-half-plane vectors by π, recording that angle; this permits full-circle atan2. |
| 35–37 | Resets or advances validity in parallel with the vector pipeline. |
| 38–39 | Creates six stages, each starting at iteration K=3*s. |
| 40–41 | First shift/add vector rotation reduces signed y toward zero. |
| 42 | Adds or subtracts the first elementary angle consistently with that rotation. |
| 43–44 | Second combinational vector rotation uses the updated y sign and shift K+1. |
| 45 | Updates accumulated angle for the second rotation. |
| 46–49 | Performs and registers the third rotation at shift K+2, advancing to the next stage. |
| 50–51 | Ends the pipeline-stage generator. |
| 52–53 | Rounds the 24-bit angle to 18 bits. Full-turn arithmetic naturally wraps at ±π. |
| 54–55 | Exports validity from the final stage. |

## laser_pll_error.sv
[Open source](../TransportPhaseLockFF.srcs/sources_1/new/laser_pll_error.sv).

| Source lines | What the hardware does |
|---|---|
| 1–11 | Defines signed phase-error detection and its clock, validity, controls and wrap-memory arm. |
| 12–25 | Returns legacy/capture/stage-3 targets, validity/saturation, 24-bit turns and full 43-bit phase for tracking. |
| 26–29 | Forms principal phase error and adjacent-sample wrapped frequency difference; keeps previous validity. |
| 30–32 | Allocates wide legacy/capture gain registers and bounded stage-3 phase. |
| 33–35 | Counts slips and exports both full phase for origin subtraction and bounded phase for the old scaler. |
| 36–40 | Runs the unchanged three-register /160 scaler for stage 3. |
| 41–44 | Sign-extends phase/frequency and forms optional legacy frequency capture. |
| 45–47 | Forms forced capture and polarity-adjusted DAC candidates. |
| 49–60 | States the frequency ambiguity bound; reset clears phase history, validity and gain registers. |
| 61–68 | Tracks valid phase, saves the previous sample, and registers phase/frequency errors without differencing across gaps. |
| 69–71 | Applies the original gain fields to stages 0/2 and aligns their validity. |
| 73–81 | Flags and saturates both legacy/capture candidates, preserving sign at maximum shifts. |

## laser_pll_unwrap.sv
[Open source](../TransportPhaseLockFF.srcs/sources_1/new/laser_pll_unwrap.sv).

| Source lines | What the hardware does |
|---|---|
| 1–4 | Defines signed 24-bit turn memory with endpoint saturation, never numeric wraparound. |
| 5–9 | Receives arm, validity and signed principal phase error. |
| 10–13 | Exports turn memory, full guarded 43-bit phase and bounded 26-bit DAC phase. |
| 14–17 | Stores previous error and subtracts in 19 bits so a nearly full-turn jump remains visible. |
| 18–21 | Starts next-state logic; disarm or missing history rebases the count to zero. |
| 22 | A jump below −π increments the winding count unless already at its positive numeric endpoint. |
| 23–24 | A jump above +π decrements it unless already at its negative endpoint. |
| 25–27 | Forms full error + turns*2^18 using the updated count on the same sample as the crossing. |
| 28–31 | Explains why bounding only the DAC representation at ±128 turns is safe when its widest linear range is ±80 turns. |
| 32–33 | Adds principal phase to the low eight signed count bits; used only for counts −127…127. |
| 34–35 | Selects signed 26-bit endpoints outside that count range. The full memory is retained. |
| 36–38 | Reset, invalid phase or disarm clears unobservable winding history. |
| 39–44 | Registers the valid principal phase and next count, then closes the block. |

## laser_pll_phase_scale.sv
[Open source](../TransportPhaseLockFF.srcs/sources_1/new/laser_pll_phase_scale.sv).

| Source lines | What the hardware does |
|---|---|
| 1–5 | Defines the stage-3 full-span mapping and its three pipeline registers. |
| 6–15 | Receives bounded phase in 2^18 codes/turn, gain, inversion and validity; returns signed DAC code and aligned flags. |
| 16–18 | Allocates the input phase register and two stages of control/valid metadata. |
| 19–22 | Uses one 26×18-bit DSP product. The constant 104858/2^26 approximates division by 640 with +3.815 ppm relative error. |
| 23 | Combines common gain 2^g with reciprocal scaling as a right shift of 26−g (11…26 bits). |
| 24 | Applies the polarity that was captured with the phase sample. |
| 25–27 | Adds half of the discarded unit, then arithmetic-shifts: nearest rounding with half ties toward +infinity. |
| 28–33 | Synchronous reset zeros data, control metadata and output flags. |
| 34–35 | First register captures bounded unwrapped phase, gain, inversion and validity. |
| 36–37 | Second register captures the reciprocal product and advances its control/valid metadata. |
| 38–39 | Third register aligns output validity and flags clipping of the actual scaled value; nonzero turns alone do not imply saturation. |
| 40–41 | Produces zero for invalid data; otherwise clamps the rounded value to −32768…32767. |
| 42–44 | Closes the sequential block and module. |

## laser_pll_fft.sv
[Open source](../TransportPhaseLockFF.srcs/sources_1/new/laser_pll_fft.sv).
| Source lines | What the hardware does |
|---|---|
| 1–4 | Defines the raw-ADC coarse spectrum branch; 1024 samples at 1.96608 GS/s give 1.92 MHz bins. |
| 5–13 | Clock/reset, eight ADC samples, raw validity and FFT amplitude threshold; outputs bin, validity and status. |
| 14–16 | Names the seven states of capture, configuration, serialization, processing and publication. |
| 17–20 | Allocates the 128×128-bit snapshot and 1024×16-bit Hann ROM; loads generated window coefficients. |
| 21–25 | Keeps capture/read addresses, synchronous memory outputs and the signed window product. |
| 26 | Selects one chronological 16-bit lane from the fetched wide word. |
| 27–28 | Captures every valid eight-sample word while in CAPTURE, without stalling the ADC. |
| 29–32 | Reads snapshot word and Hann coefficient synchronously for the current serial sample index. |
| 33–35 | Multiplies signed ADC data by a positive Q0.15 window coefficient in the next state. |
| 37–40 | Declares FFT AXIS data, indexed output metadata and fault-event wires. |
| 41–47 | Instantiates the vendor core and sends forward/scaling configuration until its handshake completes. |
| 48–50 | Sends windowed real data, zero imaginary data and the final-sample flag; holds the payload while not ready. |
| 51–54 | Accepts every FFT data/status output; no reorder buffer or downstream backpressure is needed. |
| 55–59 | Monitors overflow and bad frame markers; intentional non-realtime input pauses are not treated as faults. |
| 60–66 | Unpacks signed real/imaginary outputs and allocates two magnitude-pipeline stages with matching bin/valid/last tags. |
| 67–69 | Registers the two squared components using DSP multipliers. |
| 70 | Adds them with a guard bit to get power. |
| 71–73 | Delays the frequency-bin index and frame/valid metadata to match power. |
| 74–76 | Restricts peak and total-power statistics to bins 104…495, the requested first-zone RF band. |
| 77–82 | Stores strongest power/bin, integrated in-band power, frame faults, sequence number and result age. |
| 83–84 | Squares the programmable minimum magnitude once per clock; avoids a square-root operation on FFT power. |
| 85–88 | Requires nonzero power, the absolute threshold, and strongest-bin power at least one eighth of total band power. |
| 89–95 | Initializes the capture FSM, published estimate, statistics, sticky faults and watchdog. |
| 96–99 | Ages the estimate; an ADC gap or approximately 4.27 ms without publication invalidates it. |
| 100–103 | Rejects frames spanning input gaps or FFT errors and latches overflow/protocol diagnostics. |
| 104–106 | CAPTURE requires consecutive valid words; a gap restarts the snapshot address. |
| 107–111 | After word 127, starts configuration and clears statistics for the new transform; otherwise increments the capture address. |
| 112–115 | Waits for FFT configuration acceptance, then executes synchronous read and window multiply states. |
| 116–119 | Advances serial input only after acceptance; after sample 1023 it waits for transform output. |
| 120 | Waits for the final power-pipeline result before publishing. |
| 121–124 | Publishes peak bin and qualified validity; weak_signal describes amplitude/prominence rejection. |
| 125–129 | Increments the observable frame counter, resets age and begins another snapshot. |
| 130–133 | Accumulates power for accepted in-band bins and replaces the maximum only with a larger value. |
| 134–139 | Closes the FSM and packs signature, frame sequence, fault flags, validity and bin into GPIO status. |

## laser_pll_acquisition.sv
[Open source](../TransportPhaseLockFF.srcs/sources_1/new/laser_pll_acquisition.sv).

| Source lines | What the hardware does |
|---|---|
| 1–13 | Defines detector selection and receives coarse/fine data, control and DAC readiness. |
| 14–25 | Receives the four fine candidates, separate pipeline valid flags and 24-bit winding count. |
| 26–32 | Returns memory/tracking arm, selected DAC target and acquisition diagnostics. |
| 33–38 | Decodes stage 4 from request bit 3 and DC as mode 5 from priority bit 2. |
| 39–44 | Allocates widened coarse frequency/scaling registers; coarse error cannot wrap at the fine ambiguity limit. |
| 45–52 | Registers reference-minus-FFT-bin frequency, coarse gain and its validity. |
| 53–58 | Clips the coarse DAC code and qualifies stage 2 within ±80 MHz with valid fine data. |
| 59–64 | Defines manual fine-data readiness and five-clock wrap/scaler preparation. |
| 65–67 | Keeps wrap memory armed across stages 3↔4; prepares tracking while its request is pending. |
| 68–71 | Shifts preparation validity or resets it after invalid/disarmed data. |
| 72–78 | Defines separate active/requested multiplexers; legacy is the default. |
| 79–84 | Selects the active coarse, capture, unwrapped, tracking or literal-DC output with its own validity. |
| 85–89 | Defaults the requested candidate and applies stage-2 frequency qualification. |
| 90–93 | Requires valid prepared memory and the chosen pipeline output for stages 3/4; no frequency or dwell gate. |
| 94–96 | DC needs no detector validity; closes the request mux. |
| 97–104 | Uses the unchanged registered tracking-offset handoff for every mode change. |
| 105–107 | Packs signed turns, validity/readiness, pending, transition and the three-bit active mode. |

## laser_pll_handoff.sv
[Open source](../TransportPhaseLockFF.srcs/sources_1/new/laser_pll_handoff.sv).
| Source lines | What the hardware does |
|---|---|
| 1–4 | Defines a qualified mode change with a temporary output-continuity correction. |
| 5–10 | Receives synchronous reset/ready, desired mode, entry permission and offset-decay interval. |
| 11–15 | Receives independent requested and active detector targets with validity and active clipping status. |
| 16–21 | Exports selected mode, one registered DAC target, validity/clipping and transition-in-progress flag. |
| 22–24 | Stores an 18-bit correction (enough for opposite 16-bit rails), interval counter, and startup state. |
| 25 | Builds a 2^interval−1 mask; this makes the interval counter wrap at the requested power of two. |
| 26 | Accepts a new/initial mode only if allowed and its candidate is valid. |
| 27–28 | Adds active target and correction with headroom; transition status means the correction has not yet reached zero. |
| 29–33 | Reset mutes and clears the correction. Legacy startup remains compatible; new-stage startup awaits qualification. |
| 34–37 | Updates only on accepted DAC clocks; a mode change records the new active mode. |
| 38–41 | Initializes correction as previous output minus new target while leaving the registered output unchanged on this edge. |
| 42 | Marks the held first sample valid and restarts the decay interval. |
| 43–45 | Mutes before startup qualification or after invalid active data, clearing obsolete correction history. |
| 46–50 | In ordinary operation emits the corrected target, saturating if needed; after the ramp this is a one-cycle pass-through. |
| 51–52 | Advances the interval counter and detects each correction-step clock. |
| 53–54 | Moves the correction one code toward zero in either sign, with no overshoot. |
| 55–59 | Closes the sequential conditions. During backpressure all state and the output hold. |

## laser_pll_dac.v
[Open source](../TransportPhaseLockFF.srcs/sources_1/new/laser_pll_dac.v).
| Source lines | What the hardware does |
|---|---|
| 1–4 | Defines one independent error per clock, repeated into the RFDC C2R input format. |
| 5–11 | Receives synchronous enable/clear, selected signed target and its validity/clipping status. |
| 12–17 | AXIS output handshake and live-saturation/sticky-stall status. |
| 18–19 | Declares the final signed 16-bit DAC register and its clocked update. |
| 20–22 | Reset/mute/clear resets diagnostic flags. |
| 23–25 | Latches any DAC stall; updates clipping status on accepted output clocks. |
| 26–29 | Global reset zeros the DAC register. Data must otherwise remain stable during backpressure. |
| 30–32 | On ready, emits zero for mute/clear/invalid, otherwise the selected target; intermediate errors are discarded, not queued. |
| 33–36 | Replicates the same I code into seven 32-bit pairs, each with Q=0. |
| 37–38 | Keeps the stream valid outside global reset, including valid zero words when muted. |

## laser_pll_wrapper.v
[Open source](../TransportPhaseLockFF.srcs/sources_1/new/laser_pll_wrapper.v). Verilog module-reference shell; no arithmetic or registers.

| Source lines | What the hardware does |
|---|---|
| 1–12 | Module and Vivado metadata for existing ADC/error-DAC streams, clock and reset. |
| 13–17 | New RF-source GPIO and AXIS stream declarations. |
| 18–38 | Existing controls, IIR, IQ monitor and FRA counters. |
| 39–60 | FRA tone/reference/probe streams and original diagnostic ports. |
| 62–67 | Instantiates the SV top and connects ADC and both DAC stream interfaces. |
| 68–79 | Connects existing PLL, monitor, IIR and diagnostic words. |
| 80–90 | Connects HLS FRA streams and original diagnostic outputs. |

## laser_pll_tracking.sv
[Open source](../TransportPhaseLockFF.srcs/sources_1/new/laser_pll_tracking.sv).

| Source lines | What the hardware does |
|---|---|
| 1–6 | Defines the anchored tracking law and fixed-point units; one turn is 2^18 input phase codes. |
| 7–20 | Receives full unwrapped phase, entry DAC bias, initial sensitivity/polarity and GPIO target; emits a DAC candidate. |
| 21–25 | Stores origin, bias, positive sensitivity coefficient and interval counter. |
| 26–30 | Bounds target/initial shifts to 0..8 and interval to 0..20; constructs update mask and exact target coefficient. |
| 31–33 | Sets a <=1/256 relative coefficient step and reports whether a ramp remains. |
| 34–37 | Reset/disarm/invalid data clears unobservable origin history and restores the base coefficient. |
| 38–40 | On first valid armed sample, saves phase and DAC bias and starts at the main phase-gain setting. |
| 41–43 | Counts RF clocks between coefficient updates only while a change remains. |
| 44–46 | Increases sensitivity by the bounded relative step, stopping exactly at the target. |
| 47–52 | Decreases similarly; a changed request never jumps the coefficient. |
| 54–61 | Allocates six pipeline boundaries, a full-width origin difference, DSP product and aligned validity/polarity. |
| 62 | Rounds fixed-point product to DAC codes using the retained half-code bit. |
| 63 | Adds saved DAC bias in a width that cannot wrap before saturation. |
| 64–68 | Clears the complete candidate pipeline immediately after reset/disarm/invalid phase. |
| 69–72 | Registers full phase, then its signed 44-bit difference from the saved origin. |
| 73–74 | Bounds only the relative DAC representation to signed 26 bits (±128 turns); upstream slip memory is untouched. |
| 75 | Multiplies relative phase by the slowly changing, always-positive coefficient. |
| 76 | Registers rounded DAC deviation and applies the delayed polarity; saved bias is not inverted again. |
| 77–79 | Advances validity/polarity and marks the sixth-register output valid. |
| 80–84 | Flags and clips bias-plus-deviation to DAC range; invalid output is zero. |
| 85–86 | Packs origin initialized, ramping, clipping, valid and actual coefficient into read-only GPIO status. |

## laser_pll_monitor.sv
[Open source](../TransportPhaseLockFF.srcs/sources_1/new/laser_pll_monitor.sv).

| Source lines | What the hardware does |
|---|---|
| 1–7 | Defines finite nonblocking I/Q capture, boxcar averaging and old {I64,Q64} memory layout. |
| 8–20 | Receives post-DDC samples/valid and arm configuration; exposes independent AXIS and FIFO reset/status. |
| 21–26 | Stores one-shot capture state, latched averaging/count, window index and wide signed sums. |
| 27 | Builds the 2^D-sample window endpoint; 16 bits cover the largest 65536-sample average. |
| 28–29 | Includes each sample, substituting zero for missing input so the monitor clock grid is retained. |
| 30–31 | Arithmetic right shift divides each complete sum by the power-of-two window length. |
| 32–33 | Resets only the capture FIFO when disarmed and exposes queued-count and sticky data-quality flags. |
| 34–39 | Reset/disarm clears capture state, sums, pending AXIS word and diagnostics. |
| 40–45 | Latches settings once per arm, rejecting zero length by never starting collection. |
| 46–49 | Releases a pending word only after READY; last-word acceptance marks source completion. |
| 50–51 | Flags missing filtered data while a capture is collecting. |
| 52–53 | At a window boundary, starts the next nonoverlapping averaging interval. |
| 54–58 | If the output slot is available, sign-extends both means into the 128-bit word, asserts valid/TLAST, and counts it. |
| 59–60 | Stops after exactly N queued samples; an unavailable slot instead sets the persistent loss flag without stalling the PLL. |
| 61–68 | Otherwise accumulates the current window and closes the clocked logic/module. |

## laser_pll_fra.sv
[Open source](../TransportPhaseLockFF.srcs/sources_1/new/laser_pll_fra.sv). R7 legacy error/drive measurement plus two raw-phase modes; no new feedback registers.

| Source lines | What the hardware does |
|---|---|
| 1–9 | Defines error-output injection and existing data/validity inputs. |
| 10–12 | New CORDIC/applied RF phase, ADC rail and RF readiness inputs; RF phase-command output. |
| 13–31 | Existing window, counters, DAC command and HLS AXIS ports. |
| 32–42 | Run-state machine, window count, 4096-step envelope, faults and baseline/extrema. |
| 43–50 | Latches mode and instantiates the diagnostic-only relative-phase observer. |
| 51–54 | Defines delayed diagnostic flags and combines registered ADC rails with other saturation sources. |
| 55–59 | Joins HLS tone/reference by transaction number. |
| 61–77 | Three stimulus-only registers, aligning sine/cosine references with amplitude-ramped injection. |
| 78 | Routes injection to RF phase only in RF mode. |
| 79–82 | Existing combinational error-output addition and saturation; adds zero stimulus in RF mode. |
| 84–92 | Delays clipping flags, mode and window/busy flags to match the ADC lane registers. |
| 94–117 | Counts clipping against delayed windows; measured-sample count and DAC extrema retain their original clock. |
| 119–125 | Independent pending handshakes protect four observation streams without stalling feedback. |
| 126–133 | One-clock reference/drive delay matches the new phase observer. |
| 134–145 | Selects E/U, Phi/U or Phi_rx/Phi_tx and pairs with the correct sine/cosine reference. |
| 146–150 | Packs lane-zero observations into existing HLS streams and exports valid flags. |
| 152–162 | Resets/latches faults; tests phase, DAC readiness, RF readiness, probe room and tone continuity. |
| 163–170 | Arm saves baseline and mode; otherwise holds zero envelope. |
| 171–182 | Ramps on, waits settling interval, rejects zero-length window. |
| 183–191 | Integrates exact requested count and ramps off. |
| 192–198 | Drains 16 clocks and holds DONE until arm clears. |
| 199–206 | Abort ramps down without resetting the PLL; status includes mode/faults/envelope. |

## laser_pll_phase_probe.sv
[Open source](../TransportPhaseLockFF.srcs/sources_1/new/laser_pll_phase_probe.sv). Diagnostic relative phase only; independent of the feedback winding accumulator.

| Source lines | What the hardware does |
|---|---|
| 1–5 | States 18-bit binary-turn units and ±2-turn diagnostic range. |
| 6–12 | Declares phase input/valid, arm-active state, 20-bit relative phase and flags. |
| 13–14 | Remembers previous valid wrapped phase and whether history exists. |
| 15 | 18-bit subtraction wraps modulo one turn, correctly crossing ±pi. |
| 16 | Widens the next accumulation to 21 bits so overflow is visible. |
| 17–22 | On reset clears history; otherwise registers validity and previous valid phase. |
| 23–24 | While inactive, follows phase but zeros relative phase and saturation. |
| 25–27 | On active valid input, establishes the origin if no prior sample exists. |
| 28–29 | Rails signed 20-bit output and sets sticky saturation on either overflow. |
| 30–34 | Otherwise accumulates the signed phase step; closes logic. |

## laser_pll_rf_pm.sv
[Open source](../TransportPhaseLockFF.srcs/sources_1/new/laser_pll_rf_pm.sv). Constant-envelope I/Q for DAC229/2; four source-only registers.

| Source lines | What the hardware does |
|---|---|
| 1–5 | States phase units and alignment of applied phase with the output word. |
| 6–14 | Phase/amplitude controls, packed DAC stream, readiness and applied-phase record. |
| 15–17 | Rounds to the 16-bit ROM phase grid; adds a quarter turn for cosine. |
| 18–19 | Mirrors second/fourth quadrants into quarter-wave addresses. |
| 20–21 | Loads the existing 18-bit quarter-wave sine table into inferred block RAM. |
| 22–28 | Registers magnitudes, signs, amplitude/phase metadata, two DSP products and output I/Q. |
| 29–34 | First stage reads both ROM ports and saves signs; internal pipeline always advances. |
| 35–36 | Captures midpoint applied phase, exact zero special case, amplitude clamped at 32767. |
| 37–39 | Second stage applies quadrant signs and aligns amplitude/phase metadata. |
| 40–42 | Third stage multiplies sin/cos by amplitude and advances metadata. |
| 43 | Reset sets output I/Q and reported applied phase to zero. |
| 44–49 | Fourth stage rounds products to 16-bit codes; exact-zero PM reproduces old I=A,Q=0. Holds output on backpressure. |
| 51–54 | Repeats the same complex sample into seven chronological DAC pairs; valid follows reset. |

## laser_pll_iir.sv
[Open source](../TransportPhaseLockFF.srcs/sources_1/new/laser_pll_iir.sv). All registers use the 245.76 MHz clock; the recurrence advances on alternate edges (122.88 MS/s).

| Source lines | What the hardware does |
|---|---|
| 1–5 | States the first-order difference equation, two-step recurrence and direct bypass. |
| 6–14 | Signed DAC-code input/output, matched validity/saturation, coefficient words and control/status. |
| 15–18 | Q5.27 feed coefficients, Q1.31 pole, and signed 40-bit state with 24 fractional DAC-code bits. |
| 19–20 | Previous raw sample and previous 17-bit pair sum. |
| 21–23 | Add adjacent input codes before decimation; keeping the sum retains the half-code fractional bit. |
| 24 | Commit acknowledgment, alternating arithmetic phase and present/previous input saturation flags. |
| 25–26 | Full 49-bit feed and 72-bit recursive products map into DSPs. |
| 27 | A toggle of control bit 1 requests an atomic coefficient commit. |
| 28–29 | Sign-extend feed products before alignment; negative codes remain signed. |
| 30–31 | Align products to 55 fractional bits, including division by two for input pairs; add half a state LSB. |
| 32–33 | Round to 24 fractional bits and detect overflow using explicitly sized signed limits. |
| 34–38 | Round to a 16-bit DAC command and clamp both rails, including overflow from rounding. |
| 39–43 | Global reset initializes unity gain, zero state/history and cleared flags. |
| 44–48 | On invalid input or commit, seed state/history from the present input and restart the alternating schedule. |
| 49 | Latch all three coefficient words on one edge and acknowledge commit. |
| 50–51 | Capture every raw input sample and its saturation flag; alternate arithmetic phase without gating the clock. |
| 52–54 | First arithmetic edge: multiply current/previous pair sums and recursive state; combine saturation of both samples in the pair. |
| 55–58 | Second edge: sum, round, saturate state and align its validity/saturation. |
| 59–61 | Hold recursive output between update edges. |
| 62–64 | Select the warmed filter or direct input combinationally, including matching flags. |
| 65–66 | Status bits: selected, commit acknowledgment, saturation, valid; no sticky state in these readbacks. |

## Generated data and vendor IP
`laser_pll_fir_coeffs.vh` is a constant Q1.17 tap lookup: entries 0…31 give the 32 Kaiser-window FIR coefficients, and the default case gives zero. `scripts/generate_laser_pll_tables.py` generates it together with the midpoint quarter-wave sine table and periodic Hann ROM. The FIR coefficients sum to 131072 (unity DC gain). `.mem` rows are hexadecimal ROM contents, not sequential instructions.
`laser_pll_fft_core` is AMD xFFT 9.1 revision 12; its generated HDL is vendor code, not a handwritten SV module. The tracked XCI and `scripts/create_laser_pll_fft.tcl` specify the fixed 1024-point radix-2-lite burst implementation, arithmetic widths and AXIS options. The wrapper above documents each protocol/data operation around that IP.
