# Laser PLL RTL walkthrough
This is a source-line guide to every synthesizable handwritten PLL module. Adjacent lines forming one statement or pipeline operation are grouped. Blank lines and closing braces have no independent hardware behavior. Line numbers refer to this revision; pipeline timing and GPIO units are in [laser_pll.md](laser_pll.md).
`wire`/continuous assignments describe combinational hardware; `reg` values assigned on a rising edge describe stored state. Nonblocking assignments read the previous register values on that edge. A `for (genvar ...)` creates parallel hardware, whereas the FFT state machine deliberately reuses a serial datapath. All clocks here are 245.76 MHz.

## laser_pll.sv
[Open source](../TransportPhaseLockFF.srcs/sources_1/new/laser_pll.sv).
| Source lines | What the hardware does |
|---|---|
| 1–4 | Defines simulation time units and the top-level real-ADC phase detector. |
| 5–7 | Associates the stream interfaces and active-low reset with the RF fabric clock for Vivado. |
| 8–10 | Receives eight chronological real ADC words and the AXIS valid/ready handshake. |
| 11–13 | Exposes the seven-pair DAC stream and its ready input. |
| 14–19 | Receives staged DDS frequency, main controls, phase setpoint, acquisition controls and literal DC code. |
| 20–24 | Returns fine phase/frequency, acquisition stage/turn count, and FFT diagnostics. |
| 25–27 | Decodes enable, clear, and minimum post-mixer amplitude in ADC counts. |
| 28–30 | Declares the eight complex mixer samples, validity, DDS acknowledgment and committed FCW. |
| 31–37 | Instantiates the mixer on the global reset, allowing the DDS to keep physical time while the detector is muted. |
| 38–39 | Never backpressures the ADC. Detector history is reset on mute or clear. |
| 40–45 | Instantiates identical I/Q FIRs, both reset/qualified identically. |
| 46–47 | Computes unsigned I/Q magnitudes, including the magnitude of the most-negative signed input. |
| 48–51 | Applies the max-norm amplitude threshold with eight fractional bits and explicitly rejects zero input. |
| 52–57 | Sends qualified I/Q into full-circle atan2; the phase-valid flag follows its pipeline. |
| 59–63 | Declares three detector targets and their validity/saturation diagnostics, plus signed 24-bit turns. |
| 64–72 | Instantiates phase subtraction, derivative capture and wide-phase scaling, with independent stage-3 validity. |
| 73–78 | Taps the raw ADC into the FFT estimator. It runs while muted, but clear resets its state and sticky faults. |
| 79–89 | Connects coarse and fine candidates to stage selection. Uses the committed FCW, not half-written GPIO data. |
| 90–93 | Registers/packs the selected target for DAC 229/1 and retains stall diagnostics. |
| 94–95 | Packs the existing phase-status ABI; this valid flag describes fine phase, not wide/DC validity. |
| 96–97 | Sign-extends the 18-bit fine frequency error to a 32-bit GPIO read. |

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
| 1–4 | Defines phase/frequency detection; one turn is 2^18 phase codes. |
| 5–11 | Receives phase, validity, gain/polarity controls, setpoint and wrap-memory arm. |
| 12–17 | Returns wrapped error/frequency and the shorter legacy candidate with validity/clipping. |
| 18–24 | Returns the independently valid wide-phase target, capture target and 24-bit winding counter. |
| 25 | Subtracts the measured phase modulo one turn to form the principal error. |
| 26–28 | Keeps previous measured phase and forms a wrapped first difference; validity prevents differencing across gaps. |
| 29–31 | Allocates legacy/capture gain registers and the bounded 26-bit unwrapped representation. |
| 32–34 | Counts principal-error wraps. The DAC representation preserves phase over many turns; full 43-bit debug arithmetic is unused here. |
| 35–39 | Instantiates the three-register stage-3 scaler. Passes aligned validity, gain and polarity; output slope is reduced by 160. |
| 40–41 | Sign-extends phase and derivative so maximum GPIO gains cannot overflow the working representation. |
| 42–43 | Forms the legacy detector with an optional derivative. |
| 44–46 | Forms forced capture and converts the existing registered candidates to signed DAC units, including inversion. |
| 48–50 | States the consecutive-sample frequency ambiguity bound and starts the synchronous detector. |
| 51–59 | Reset clears phase history, valid flags and legacy/capture gain registers. |
| 60–67 | Tracks validity, stores measured phase, and registers wrapped error and derivative. |
| 68–70 | Applies common phase gain to stages 0/2 and aligns their target validity. |
| 71–73 | Closes sequential logic; 49-bit working values preserve both maximum gain shifts. |
| 74–76 | Flags/clamps the legacy DAC output instead of allowing sign wrap. |
| 77–80 | Flags/clamps the forced-capture output and closes the module. |

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
| 1–3 | Defines coarse/fine/DC selection without reference retuning or feedback filtering. |
| 4–13 | Receives clock/reset/ready, controls, committed reference frequency and coarse/fine validity. |
| 14–22 | Receives candidate DAC codes/clipping and separate validity for the longer stage-3 pipeline, plus winding count. |
| 23–28 | Returns arm, selected output, validity/clipping and acquisition status. |
| 29–33 | Selects DC as internal mode 4 or a requested stage 0…3. |
| 34–39 | Allocates widened coarse-frequency/gain registers and their validity flags. |
| 40–47 | Subtracts the FFT frequency from the reference in 937.5 Hz codes, registers independent coarse gain and aligns validity. |
| 48–50 | Clamps the coarse candidate into DAC range and flags clipping. |
| 51–53 | Allows stage 2 inside ±80 MHz when the FFT and fine target are valid. |
| 54–57 | Keeps stage-3 entry manual; fine_ready reports fine input/legacy-target validity, and preparation has five bits. |
| 58–60 | Arms memory while stage 3 is active or a valid request is pending. |
| 61–64 | Requires five valid armed clocks to prepare the counter and longer scaler before handoff. |
| 65–71 | Declares/defaults independent active and requested target multiplexers. |
| 72–76 | Selects the active coarse, capture, unwrapped or DC candidate. Stage 3 uses its own delayed validity; DC is always valid. |
| 77–81 | Builds the requested candidate and applies the existing stage-2 qualification. |
| 82–83 | Requires both the new scaler valid flag and prepared memory for stage-3 acceptance. |
| 84–86 | DC bypass needs no detector validity; closes the target mux. |
| 87–94 | Runs the common one-register continuous handoff for all stages. |
| 95–97 | Packs the full winding counter and live status flags into GPIO. |

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
[Open source](../TransportPhaseLockFF.srcs/sources_1/new/laser_pll_wrapper.v).
| Source lines | What the hardware does |
|---|---|
| 1–3 | Supplies the Verilog top boundary needed for this Vivado module reference. |
| 4–6 | Declares stream clock association and active-low reset metadata. |
| 7–12 | Declares the ADC and DAC AXIS ports with the same widths as laser_pll.sv. |
| 13–18 | Declares staged frequency and detector/acquisition/DC control ports for GPIO wiring. |
| 19–23 | Declares four 32-bit GPIO status outputs. |
| 24–28 | Instantiates the SystemVerilog top and passes clocks, reset and stream handshakes directly. |
| 29–30 | Passes control words directly; no new registers, clock crossings or latency. |
| 31–34 | Passes status words directly and closes the wrapper. |

## Generated data and vendor IP
`laser_pll_fir_coeffs.vh` is a constant Q1.17 tap lookup: entries 0…31 give the 32 Kaiser-window FIR coefficients, and the default case gives zero. `scripts/generate_laser_pll_tables.py` generates it together with the midpoint quarter-wave sine table and periodic Hann ROM. The FIR coefficients sum to 131072 (unity DC gain). `.mem` rows are hexadecimal ROM contents, not sequential instructions.
`laser_pll_fft_core` is AMD xFFT 9.1 revision 12; its generated HDL is vendor code, not a handwritten SV module. The tracked XCI and `scripts/create_laser_pll_fft.tcl` specify the fixed 1024-point radix-2-lite burst implementation, arithmetic widths and AXIS options. The wrapper above documents each protocol/data operation around that IP.
