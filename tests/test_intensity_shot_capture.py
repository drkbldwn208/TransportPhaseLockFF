"""RTL shot monitor: triggered records, bounded memory and loss detection."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
source = root/'TransportPhaseLockFF.srcs/sources_1/new'
work = root/'build/intensity_linearized/sim_shots'
work.mkdir(parents=True, exist_ok=True)
vivado_bin = Path('/home/levlabcukomen/tools/Vivado/2024.1/bin')
commands = [
    ['xvlog', '--sv', str(source/'intensity_shot_capture.sv'), str(root/'tests/intensity_shot_capture_tb.sv')],
    ['xelab', 'intensity_shot_capture_tb', '-s', 'shots'],
    ['xsim', 'shots', '-runall'],
]
for command in commands:
    result = subprocess.run([str(vivado_bin/command[0]), *command[1:]], cwd=work,
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (work/(command[0]+'.log')).write_text(result.stdout)
    if result.returncode or 'Fatal:' in result.stdout:
        raise RuntimeError(result.stdout[-6000:])
assert 'PASS:' in result.stdout
print(next(line for line in result.stdout.splitlines() if line.startswith('PASS:')))
