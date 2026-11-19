#!/usr/bin/env python3
"""Write the optional SKY130 test fixture; no latch knowledge lives in the MCP server."""
import argparse
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))


def build(model):
    model=str(Path(model).resolve())
    if any(c in model for c in ['"','\n','\r']):
        raise ValueError('Invalid model path')
    core=(ROOT/'circuits/strongarm.spice').read_text()
    return f'''StrongArm test fixture for the general ngspice MCP server
.lib "{model}" tt
.temp 27
.options reltol=1e-5 abstol=1e-13 vntol=1e-7 method=trap
VDD vdd 0 1.8
VCLK clk 0 PULSE(0 1.8 10n 100p 100p 9.8n 20n)
VOS inp inp_ext 0.043
VINP inp_ext 0 dc 0 external
VINN inn 0 dc 0 external
XDUT inp inn clk outp outn vdd 0 strongarm
COUTP outp 0 10f
COUTN outn 0 10f
.save v(clk) v(inp_ext) v(inp) v(inn) v(outp) v(outn) v(xdut.n_inp) v(xdut.n_inn) v(xdut.tail) i(VDD)
{core}
.end
'''

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sky130-lib',required=True,type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'runs/mcp-strongarm.cir')
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(build(args.sky130_lib))
    print(args.output.resolve())
