import numpy as np
import scipy.signal as signal
import matplotlib.pyplot as plt

def generate_cic_comp_coe(R, M, N, fc, fs_out, num_taps, filename="cic_comp.coe"):
    num_points = 2000
    f = np.linspace(0, .5, num_points)

    # Calculate the CIC filter response
    f[0] = 1e-10  # Avoid division by zero
    cic_response = np.abs((np.sin(np.pi * M * R * f / R) / np.sin(np.pi * f / R)) ** N)
    cic_response /= np.max(cic_response)  # Normalize
    f[0] = 0  # Restore original value

    nyq = fs_out / 2
    fc_norm = fc / nyq

    desired_response = np.zeros(num_points)
    passband_idx = f <= (fc_norm/2)
    desired_response[passband_idx] = 1.0 / cic_response[passband_idx]

    weight = np.ones(num_points)
    weight[passband_idx] = 100

    taps = signal.firwin2(num_taps, f, desired_response, fs=1.0, window=('kaiser', 9.0))

    bit_width=18
    max_val = 2**(bit_width - 1) - 1
    fixed_taps = np.round(taps * max_val).astype(int)

    with open(filename, 'w') as file:
        file.write("radix=10;\n")
        file.write("coefdata=\n")
        file.write(",\n".join(map(str, fixed_taps)))
        file.write(";\n")

    return taps, f, cic_response

#Plot the frequency response
def plot_frequency_response(R, M, N, fc, fs_out, num_taps):
    taps, f_norm, cic_response = generate_cic_comp_coe(R, M, N, fc, fs_out, num_taps)

    f_hz = f_norm * fs_out 

    w, h_comp = signal.freqz(taps, worN=f_hz, fs=fs_out)

    total_response = cic_response * np.abs(h_comp)

    plt.figure(figsize=(10, 6))
    plt.plot(f_hz, 20*np.log10(cic_response), label='CIC Response', linestyle='--')
    plt.plot(w, 20*np.log10(np.abs(h_comp)), label='Compensation Filter Response', linestyle='-.')
    plt.plot(w, 20*np.log10(total_response), label='Total Response', color='red')
    plt.title('CIC Filter Compensation Frequency Response')
    plt.axvline(fc/2, color='r', linestyle=':', label=f'Passband Edge ({fc/2000:,.0f} kHz)')
    plt.xlabel('Frequency (Hz)')
    plt.ylabel('Magnitude (dB)')
    plt.grid()
    plt.legend()
    plt.show()

plot_frequency_response(R=256, M=1, N=4, fc=200e3, fs_out=960e3, num_taps=127)