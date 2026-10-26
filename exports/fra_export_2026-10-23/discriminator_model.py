"""Ideal stage-4 phase detector at the measured 4x slope, IIR bypassed.

Input phase is beat minus reference, in radians (primary zone-1 input).
The recorded invert=True makes error slope positive in DAC codes/rad.
The total electronics model adds only processing absent from the loopback.
This assumes envelope delay represents small-signal phase delay; it is not
a measured RF-PM response. Neither function includes frequency-to-phase 1/s.
"""
import numpy as np

CLOCK_HZ = 245.76e6
TRACKING_COEFFICIENT = 419432
GAIN_CODES_PER_RAD = TRACKING_COEFFICIENT/(256*2*np.pi)
# Registered I/Q n+7 -> error/handoff n+22. Formatter is in the loopback.
POST_IQ_CLOCKS = 15  # CORDIC 7 + phase subtraction 1 + tracking 6 + handoff 1
POST_IQ_DELAY_S = POST_IQ_CLOCKS/CLOCK_HZ


def post_iq_response(frequency_hz):
    """Filtered I/Q phase -> pre-injection error, DAC codes/rad."""
    return GAIN_CODES_PER_RAD*np.exp(-2j*np.pi*np.asarray(frequency_hz)*POST_IQ_DELAY_S)


def electronics_response(frequency_hz, *, loopback_delay_s):
    """Lumped electronics model, DAC codes/rad, using one fitted fixture delay.

    loopback_delay_s includes converters, DAC formatter and receive mixer/FIR.
    Do not multiply this result by post_iq_response or another loopback model.
    Convert to V/rad only with a separately justified signed volts/code value.
    """
    total_delay_s = float(loopback_delay_s)+POST_IQ_DELAY_S
    return GAIN_CODES_PER_RAD*np.exp(-2j*np.pi*np.asarray(frequency_hz)*total_delay_s)
