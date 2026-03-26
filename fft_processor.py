# FFT 수학 연산 
import numpy as np
from scipy.signal.windows import flattop

def get_window(window_type: str, size: int):
    window_type = window_type.lower()
    if window_type == "hann": return np.hanning(size)
    elif window_type == "hamming": return np.hamming(size)
    elif window_type == "blackman": return np.blackman(size)
    elif window_type == "flattop": return flattop(size)
    elif window_type == "none": return np.ones(size)
    else: return np.hanning(size)

def compute_fft_data(samples, sample_rate: int, window_type: str = "hann"):
    if len(samples) < 2: return []
    
    x = np.array(samples, dtype=float)
    x -= np.mean(x)
    window = get_window(window_type, len(x))
    xw = x * window
    
    rfft = np.fft.rfft(xw)
    freqs = np.fft.rfftfreq(len(xw), d=1/sample_rate)
    mags = np.abs(rfft) / len(xw)
    
    return [{"frequency": round(float(f), 2), "magnitude": round(float(m), 4)} for f, m in zip(freqs, mags)]