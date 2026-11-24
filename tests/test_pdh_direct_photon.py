"""Actual XPM CDC simulation; direct DDS numerical check; async photon inputs."""
from pathlib import Path
import shutil
import subprocess
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'TransportPhaseLockFF.srcs/sources_1/new'
WORK=ROOT/'build/pdh_direct_tests'
VIVADO=Path('/home/levlabcukomen/tools/Vivado/2024.1')
WORK.mkdir(parents=True,exist_ok=True)
shutil.copy2(SRC/'pdh_quarter_cos.mem',WORK)
for top, files in (
    ('pdh_direct_tb',['gpio_word_cdc.v','pdh_phase_accumulator.sv','pdh_cosine_pair.sv','pdh_tones.sv']),
    ('photon_counter_tb',['gpio_word_cdc.v','pmod_edge_detect.v','pmod_debounce_sync.v','hist_counter.v']),
):
    sources=[str(SRC/f) for f in files]+[str(ROOT/'tests'/f'{top}.sv')]
    for args in (
        ['xvlog','--sv',str(VIVADO/'data/verilog/src/glbl.v'),str(VIVADO/'data/ip/xpm/xpm_cdc/hdl/xpm_cdc.sv'),*sources],
        ['xelab',top,'glbl','-s',top],['xsim',top,'-runall'],
    ):
        r=subprocess.run([str(VIVADO/'bin'/args[0]),*args[1:]],cwd=WORK,capture_output=True,text=True)
        (WORK/f'{top}_{args[0]}.log').write_text(r.stdout+r.stderr)
        if r.returncode or 'Fatal:' in r.stdout:raise RuntimeError((r.stdout+r.stderr)[-6000:])
    assert 'PASS:' in r.stdout
    print(r.stdout[-1500:])


def unpack(word,width,n,signed=False):
    value=int(word,16)
    a=np.array([(value>>(width*k))&((1<<width)-1) for k in range(n)],dtype=np.int64)
    return np.where(a>=(1<<(width-1)),a-(1<<width),a) if signed else a


def cosine(phase48):
    # Reference computes full-circle bin centres directly, independently of
    # quadrant folding used by RTL.
    phase14=phase48>>34
    return np.rint(32767*np.cos(2*np.pi*(phase14+.5)/16384)).astype(np.int64)


rows=[line.split() for line in (WORK/'pdh_direct_samples.txt').read_text().splitlines()]
checked=0
for j in range(6,len(rows)):
    source,output=rows[j-6],rows[j]
    if source[1]!=output[1]:continue
    c=unpack(source[2],48,14);m=unpack(source[3],48,14);r=unpack(source[4],48,8)
    offset=int(source[5],16)
    # Reference adds phase at 16-bit precision before reducing to 14 bits.
    r=(((r>>32)+offset)&65535)<<32
    expected=(18000*cosine(c)+7000*cosine(m)+16384)>>15
    expected_ref=(12000*cosine(r)+16384)>>15
    actual=unpack(output[6],16,14,True);actual_ref=unpack(output[7],16,8,True)
    assert np.array_equal(actual,expected),(j,actual[:3],expected[:3])
    assert np.array_equal(actual_ref,expected_ref),(j,actual_ref[:3],expected_ref[:3])
    # Check lane timing and coherence independently of the cosine lookup.
    c_now=unpack(output[2],48,14);m_now=unpack(output[3],48,14);r_now=unpack(output[4],48,8)
    c_fcw=int(rows[j-2][8],16);m_fcw=int(rows[j-2][9],16)
    mask=(1<<48)-1
    assert np.array_equal((c_now-c_now[0])&mask,(np.arange(14)*c_fcw)&mask)
    assert np.array_equal((m_now-m_now[0])&mask,(np.arange(14)*m_fcw)&mask)
    assert r_now[0]==m_now[0]
    assert np.array_equal((r_now-r_now[0])&mask,((np.arange(8)*14*m_fcw)//8)&mask)
    checked+=1
print(f'PASS: {checked} exact DDS words, all 22 lanes, including up/down frequency slews.')
