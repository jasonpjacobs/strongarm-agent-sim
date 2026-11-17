"""Portable SPICE fixture; no simulator, PDK, or model files are bundled."""
import math
from .config import ROOT, load, require

def build(offset_V=.043, max_step_s=5e-12, reltol=1e-5):
    model = require(load(), 'sky130_lib')
    if any(c in model for c in ['"', '\n', '\r']):
        raise ValueError('Model path cannot contain quotes or newlines')
    if not all(map(math.isfinite, [offset_V, max_step_s, reltol])) or max_step_s <= 0 or reltol <= 0:
        raise ValueError('Invalid numerical fixture settings')
    core = (ROOT/'circuits/strongarm.spice').read_text()
    return f'''StrongArm agent-in-the-simulation testbench
.lib "{model}" tt
.temp 27
.options reltol={reltol:.17g} abstol=1e-13 vntol=1e-7 method=trap
VDD vdd 0 1.8
VCLK clk 0 PULSE(0 1.8 10n 100p 100p 9.8n 20n)
VOS inp inp_ext {offset_V:.17g}
* External callback supplies the entire voltage; DC is additive in ngspice.
VINP inp_ext 0 dc 0 external
VINN inn 0 dc 0 external
XDUT inp inn clk outp outn vdd 0 strongarm
COUTP outp 0 10f
COUTN outn 0 10f
.save v(clk) v(inp_ext) v(inp) v(inn) v(outp) v(outn) v(xdut.n_inp) v(xdut.n_inn) v(xdut.tail) i(VDD)
.tran {max_step_s:.17g} 2u 0 {max_step_s:.17g}
{core}
.end
'''

def canonical(text):
    return text.replace(require(load(), 'sky130_lib'), '${SKY130_MODEL_LIBRARY}')
