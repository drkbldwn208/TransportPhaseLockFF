"""Numerical validation: sensor nonlinearity, drift cancellation, sign and delay."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, Mock
from types import SimpleNamespace
import tempfile
import csv
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python_scripts'))
import intensity_calibration as ic


def synthetic(incident=1.0, delay_s=0.0, drift=0.0):
    fs=480000.;n=48000;f=1000.;t=np.arange(n)/fs;phase=2*np.pi*f*t+0.37
    u=np.round(10000+100*np.cos(phase)).astype(np.int16)
    c=np.round(10000-300*np.cos(phase)).astype(np.int16)
    p=incident*(1+drift*(t-t.mean())/np.ptp(t))*((10000+100*np.cos(phase-2*np.pi*f*delay_s))/20000)**2
    sensor=np.round(1000+12000*np.sqrt(p)).astype(np.int16)
    raw=np.zeros((n,4),np.uint32)
    lanes=np.repeat(sensor[:,None],4,axis=1).astype(np.int16)
    raw[:,:2]=lanes.view(np.uint32)
    raw[:,2]=c.astype(np.uint16).astype(np.uint32)|(u.astype(np.uint16).astype(np.uint32)<<16)
    raw[:,3]=np.round(np.remainder(phase,2*np.pi)/(2*np.pi)*2**32).astype(np.uint32)
    x=np.linspace(1000,30000,1000);table=ic.sensor_table(x,((x-1000)/12000)**2)
    return dict(raw=raw,sample_rate_hz=fs,status=2),table


class Analysis(unittest.TestCase):
    def test_incident_power_cancels_after_samplewise_sensor_calibration(self):
        values=[]
        for incident in (0.7,1.,3.):
            record,table=synthetic(incident,drift=.02)
            result=ic.analyze(record,table)
            self.assertAlmostEqual(result['loop'].real,3,delta=.005)
            # C and U are independently rounded to DAC codes in the mock.
            self.assertLess(abs(result['loop'].imag),.002)
            self.assertAlmostEqual(result['K'].real,2/10000,delta=8e-7)
            self.assertAlmostEqual(result['power_drift_fraction'],.02,delta=.001)
            values.append(result['K'].real)
        self.assertLess(np.ptp(values)/np.mean(values),.004)

    def test_delay_is_not_mistaken_for_static_slope(self):
        r,table=synthetic(delay_s=20e-6)
        k=ic.analyze(r,table)['K']
        self.assertAlmostEqual(np.angle(k),-2*np.pi*1000*20e-6,delta=.003)

    def test_offset_and_nonlinearity_matter(self):
        r,table=synthetic()
        correct=ic.analyze(r,table)
        uncal=ic.analyze(r)
        self.assertTrue(np.isnan(uncal['K'].real))
        raw_slope=(uncal['Q']/(uncal['p0']*uncal['U'])).real
        self.assertGreater(abs(raw_slope/correct['K'].real-1),.4)

    def test_conversion_precedes_averaging(self):
        table=ic.sensor_table([0,10000,20000],[0,1,4])
        lanes=np.array([[0,20000,0,20000]])
        self.assertEqual(ic.linearize(lanes,table)[0],2)
        self.assertEqual(np.interp(lanes.mean(),table['adc_counts'],table['optical_power']),1)

    def test_flags_and_no_extrapolation(self):
        r,table=synthetic();r['status']|=1<<4
        self.assertIn('actuator clipping',ic.analyze(r,table)['flags'])
        with self.assertRaises(ValueError):ic.linearize(np.array([[32000]]),table)
        r['raw'][:,0]=np.uint32(32000 | (32000<<16))
        flagged=ic.analyze(r,table)
        self.assertTrue(np.isnan(flagged['Q'].real))
        self.assertTrue(np.isfinite(flagged['U']))
        r['status']=2
        with self.assertRaises(ValueError):ic.analyze(r,table)

    def test_capture_plans(self):
        for f in np.geomspace(10,1e6,200):
            p=ic.plan(f)
            self.assertLessEqual(p['samples'],1048575)
            self.assertGreaterEqual(p['sample_rate_hz'],16*p['frequency_hz'])
            self.assertGreaterEqual(p['duration_s']*p['frequency_hz'],15.99)

    def test_signed_reconstruction_and_inverse(self):
        u=np.arange(2000,20001,200);k=2/u
        table=ic.reconstruct(u,k,maximum_gap_codes=250)
        self.assertLess(np.max(abs(table['F_relative']-(u/u[-1])**2)),.001)
        self.assertAlmostEqual(float(ic.inverse_command(table,.25)),10000,delta=3)
        negative=ic.reconstruct(u,-np.ones_like(u)/5000,maximum_gap_codes=250)
        self.assertGreater(negative['F_relative'][0],negative['F_relative'][-1])
        with self.assertRaises(ValueError):ic.inverse_command(table,1.1)
        with self.assertRaises(ValueError):ic.reconstruct([1,2,3],[1,-1,1],maximum_gap_codes=5)

    def test_repeated_blocks_reject_faults_and_preserve_complex_ratios(self):
        calls=[]
        def point(ol,f,**kw):
            calls.append(kw)
            # Changing incident power cancels only if Q is normalized per block.
            p0=1.0+0.1*len(calls)
            u=10+0.01*(-1)**len(calls)
            r=dict(U=complex(u),C=complex(-3*u),D=complex(4*u),Q=complex(.002*p0*u),
                   K=complex(.002),p0=p0,u0_codes=10000.,frequency_hz=f,
                   power_drift_fraction=.01,command_drift_codes=500. if len(calls)==2 else 0.,flags=['actuator clipping'] if len(calls)==1 else [],
                   fit_u_sem_codes=.01)
            Path(kw['raw_path']).write_bytes(b'raw test marker')
            return r
        with tempfile.TemporaryDirectory() as d,patch.object(ic,'configuration',return_value={}),patch.object(ic,'measure_point',side_effect=point):
            path=Path(d)/'sweep.csv'
            rows=ic.sweep(object(),[1000],table={'calibrated':True},repeats=3,max_repeats=8,csv_path=path)
            self.assertAlmostEqual(rows[0]['K'].real,.002)
            self.assertAlmostEqual(rows[0]['loop'].real,3)
            self.assertEqual(rows[0]['accepted_blocks'],3)
            self.assertEqual(rows[0]['attempts'],5)
            self.assertTrue(rows[0]['reliable'])
            with path.with_name('sweep_blocks.csv').open() as stream:blocks=list(csv.DictReader(stream))
            self.assertEqual(blocks[0]['accepted'],'False')
            self.assertEqual(blocks[1]['rejection_reason'],'command drift')
            self.assertEqual(len(list(path.with_suffix('').glob('*.npz'))),5)

    def test_unresolved_denominator_does_not_pass_quality(self):
        n=[0]
        def point(ol,f,**kw):
            n[0]+=1;u=complex((-1)**n[0])
            return dict(U=u,C=-32+u,D=32+0j,Q=.1+0j,K=.1/u,p0=1.,u0_codes=10000.,
                        frequency_hz=f,power_drift_fraction=0.,command_drift_codes=0.,flags=[])
        with tempfile.TemporaryDirectory() as d,patch.object(ic,'configuration',return_value={}),patch.object(ic,'measure_point',side_effect=point):
            row=ic.sweep(object(),[100],table={'calibrated':True},repeats=2,max_repeats=4,csv_path=Path(d)/'low.csv')[0]
            self.assertFalse(row['reliable']);self.assertFalse(row['loop_reliable'])
            self.assertTrue(np.isnan(row['loop'].real))


    def test_bad_sweep_plan_rejected_before_hardware_access(self):
        for kw in (dict(amplitude_codes=32.5), dict(repeats=2.5),
                   dict(target_snr=float('nan')), dict(cycles=float('nan'))):
            with self.assertRaises(ValueError):ic.sweep(object(),[1000],**kw)
        with self.assertRaises(ValueError):ic.sweep(object(),[1000,2e6])

    def test_bins_preserve_sign_and_reject_unresolved_response(self):
        base=dict(accepted=True,K=-.002+0j,U=10+0j,Q=-.02+0j,
                  fit_u_sem_codes=.01,fit_q_sem=.0001,u0_codes=10000.)
        bins=ic.bin_slopes([base]*3)
        self.assertAlmostEqual(bins[0]['k_per_code'],-.002)
        self.assertEqual(ic.bin_slopes([dict(base,fit_q_sem=1.)]*3),[])
        self.assertEqual(ic.bin_slopes([dict(base,K=.002j)]*3),[])

    def test_capture_disarms_and_frees_buffer_on_dma_error(self):
        class Buffer(np.ndarray):
            def freebuffer(self):self.freed=True
        for fault in (False,True):
            buffer=np.zeros((64,4),np.uint32).view(Buffer);buffer.freed=False
            registers={0:1,8:(64<<12)|2|(1<<4)}
            ctrl=SimpleNamespace(read=lambda a:registers[a],write=lambda a,v:registers.__setitem__(a,v))
            channel=Mock(running=True,idle=not fault)
            dma=SimpleNamespace(recvchannel=channel,mmio=Mock())
            dma.mmio.read.return_value=0x10 if fault else 0
            ol=SimpleNamespace(intensity_control=ctrl,intensity_dma=dma,intensity_counts=Mock())
            ol.intensity_counts.read.return_value=7
            with patch.object(ic,'check'),patch.dict(sys.modules,{'pynq':SimpleNamespace(allocate=lambda **k:buffer)}):
                if fault:
                    with self.assertRaisesRegex(RuntimeError,'DMA transfer error'):ic.capture(ol,samples=64)
                    channel.stop.assert_called_once();channel.start.assert_called_once()
                else:
                    result=ic.capture(ol,samples=64)
                    self.assertEqual(result['clip_samples'],7)
                    self.assertTrue(result['status']&(1<<4))
                    self.assertEqual(result['raw'].shape,(64,4))
            self.assertTrue(buffer.freed)
            self.assertEqual(registers[0],1)  # Arm cleared, independent tone retained.

    def test_point_failure_removes_tone_without_touching_pi(self):
        config=dict(pi_registers={'0x10':1},gpio={'9':[0,0],'11':[1,5000]},limits_word=0x7fff0000)
        regs={0:0,8:0}
        writes=[]
        def write(a,v):regs[a]=v;writes.append((a,v))
        ol=SimpleNamespace(intensity_control=SimpleNamespace(read=lambda a:regs[a],write=write),
                           intensity_tone=Mock(),fast_servo_controller_0=Mock())
        with patch.object(ic,'check'),patch.object(ic,'configuration',return_value=config), \
             patch.object(ic,'capture',side_effect=RuntimeError('test transfer failure')),patch.object(ic.time,'sleep'):
            with self.assertRaisesRegex(RuntimeError,'test transfer failure'):ic.measure_point(ol,1000)
        self.assertEqual(writes[0],(0,1));self.assertEqual(regs[0],0)
        ol.fast_servo_controller_0.write.assert_not_called()


if __name__=='__main__':unittest.main()
