"""Execute delivered notebook cells with a synthetic optical plant, no hardware.

Real fitting, repeated-block rejection, calibration, CSV/NPZ and inverse exports
run unchanged. Only the board registers, DMA samples and wall-clock waits are
modeled. This is not validation of the RFDC or optical apparatus.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault('MPLCONFIGDIR','/tmp/intensity_test_mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python_scripts'))
import intensity_calibration as ic
OUTPUT=ROOT/'build/intensity_fra/notebook_test'
OUTPUT.mkdir(parents=True,exist_ok=True)
cells=json.loads((ROOT/'python_scripts/intensity_calibration.ipynb').read_text())['cells']
for index,c in enumerate(cells):
    if c['cell_type']=='code':compile(''.join(c['source']),f'notebook cell {index}','exec')


class Registers:
    def __init__(self,values=None):self.values=values or {};self.writes=[]
    def read(self,a):return self.values.get(a,0)
    def write(self,a,v):self.values[a]=v;self.writes.append((a,v))


def tile():
    return SimpleNamespace(blocks=[SimpleNamespace(MixerSettings={'Freq':80.,'PhaseOffset':0.},
                           UpdateEvent=Mock()) for _ in range(4)],StartUp=Mock())

ol=SimpleNamespace(ip_dict={name:{} for name in ('intensity_control','intensity_tone',
    'intensity_limits','intensity_counts','intensity_dma')},
    intensity_control=Registers(),intensity_tone=Registers(),
    intensity_limits=Registers({0:0x7fff0000,8:ic.FEATURE_VERSION}),
    fast_servo_controller_0=Registers({0x10:1}),
    usp_rf_data_converter_0=SimpleNamespace(adc_tiles=[tile()],dac_tiles=[tile()]))
for n in (9,10,11,12):setattr(ol,f'axi_gpio_{n}',Registers())
ol.axi_gpio_11.values={0:1,8:10000}
state={'dark_calibration':False,'power':0.,'block':0}


def capture(overlay,*,samples,decimation_log2):
    fs=ic.FS_HZ/2**decimation_log2
    t=np.arange(samples)/fs
    phase=2*np.pi*(ol.intensity_tone.read(0)*ic.FS_HZ/2**32)*t+.37
    u0=float(ol.axi_gpio_11.read(8))
    amplitude=ol.intensity_tone.read(8)
    if amplitude>=32768:amplitude-=65536
    if not ol.intensity_control.read(0)&1:amplitude=0
    frequency_hz=ol.intensity_tone.read(0)*ic.FS_HZ/2**32
    L=3/(1+1j*frequency_hz/1e4)
    U=amplitude/(1+L);C=U-amplitude
    u=np.rint(u0+np.real(U*np.exp(1j*phase))).astype(np.int16)
    c=np.rint(u0+np.real(C*np.exp(1j*phase))).astype(np.int16)
    # Slow incident power differences between blocks, no coherent upstream line.
    state['block']+=1
    incident=1+0.001*(-1)**state['block']
    delayed_command=np.rint(u0+np.real(U*np.exp(1j*(phase-2*np.pi*frequency_hz*1e-6))))
    power=incident*(delayed_command/20000)**2
    if state['dark_calibration']:power=np.full(samples,state['power'])
    sensor=np.rint(1000+12000*np.sqrt(power)).astype(np.int16)
    raw=np.zeros((samples,4),np.uint32)
    raw[:,:2]=np.repeat(sensor[:,None],4,axis=1).view(np.uint32)
    raw[:,2]=c.astype(np.uint16).astype(np.uint32)|(u.astype(np.uint16).astype(np.uint32)<<16)
    raw[:,3]=np.rint(np.remainder(phase,2*np.pi)*2**32/(2*np.pi)).astype(np.uint32)
    return dict(raw=raw,sample_rate_hz=fs,decimation_log2=decimation_log2,
                status=2|(samples<<12),clip_samples=0,invalid_samples=0)

fake_pynq=SimpleNamespace(Overlay=Mock(return_value=ol))
clock_api=SimpleNamespace(lmk_devices=[{'compatible':'lmk'}],lmx_devices=[{}],_Config={'lmk':{}},
                          _find_devices=Mock(),_read_tics_output=Mock())
fake_xrfclk=SimpleNamespace(xrfclk=clock_api,set_ref_clks=Mock())
ns={'ol':ol,'display':lambda x:None}
old=Path.cwd()
try:
    os.chdir(OUTPUT)
    # Import/reload is itself part of the delivered notebook workflow.
    exec(''.join(cells[1]['source']),ns)
    with patch.dict(sys.modules,pynq=fake_pynq,xrfclk=fake_xrfclk,xrfdc=SimpleNamespace(EVENT_MIXER=1)), \
         patch.object(ic,'capture',side_effect=capture),patch.object(ic.time,'sleep'), \
         contextlib.redirect_stdout(io.StringIO()):
        for index,cell in enumerate(cells[2:],2):
            if cell['cell_type']!='code':continue
            source=''.join(cell['source'])
            source=source.replace('save_working_setup = False','save_working_setup = True')
            source=source.replace('np.geomspace(10, 1e6, 61)','np.array([100., 1000., 10000.])')
            source=source.replace('setpoints_counts = []','setpoints_counts = [8000, 8512, 9024, 9536, 10048]')
            source=source.replace('quasi_static_and_revisits_verified = False','quasi_static_and_revisits_verified = True')
            if source.startswith('# Run once per manually measured power point'):
                state['dark_calibration']=True
                for sensor_counts in np.linspace(1000,31000,61):
                    state['power']=float(((sensor_counts-1000)/12000)**2)
                    with patch('builtins.input',return_value=str(state['power'])):exec(source,ns)
                state['dark_calibration']=False
            else:exec(compile(source,f'notebook cell {index}','exec'),ns)
        assert ol.intensity_control.read(0)==0
        assert not ol.fast_servo_controller_0.writes
        fake_xrfclk.set_ref_clks.assert_not_called();fake_pynq.Overlay.assert_not_called()
        output=ns['output_dir']
        assert (output/'aom_inverse_lut.csv').exists()
        assert (output/'aom_relative_transmission.csv').exists()
        assert (output/'intensity_fra.png').exists()
        assert len(ns['binned'])>=3
        assert all(row['reliable'] for row in ns['rows'])
        # Exercise explicit cold-start restore too; it is allowed to reset the PI.
        clock_file=OUTPUT/'clock.txt';clock_file.write_text('Register0 0x1234\n')
        startup=''.join(cells[5]['source']).replace('download_hardware = False','download_hardware = True')
        startup=startup.replace('/home/xilinx/jupyter_notebooks/LMK_245_76_ExtRef10.txt',str(clock_file))
        exec(startup,ns)
        fake_xrfclk.set_ref_clks.assert_called_once_with(lmk_freq=245.761,lmx_freq=491.52)
        assert clock_api._Config['lmk'][245.761]==[0x1234]
        assert ol.fast_servo_controller_0.read(0x10)==1
        assert ol.axi_gpio_11.read(8)==10000
        assert ol.intensity_control.read(0)==0
    print('PASS: complete intensity notebook, attach without writes, explicit cold-start restore, synthetic sensor/AOM, repeated FRA, NPZ/CSV/PNG and inverse-table export')
    print('Synthetic output:',(OUTPUT/ns['output_dir']).resolve())
finally:
    os.chdir(old);plt.close('all')
