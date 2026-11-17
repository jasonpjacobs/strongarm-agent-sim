# Third-party references and external dependencies

This repository's authored source, circuit description, schematics, documentation and sanitized example are distributed under the MIT license in `LICENSE`.

- The 11T StrongArm topology and initial device sizes were informed by the public [niztg/Sky130-SAR-ADC comparator testbench](https://github.com/niztg/Sky130-SAR-ADC/blob/main/strongarm_comparator_tb.spice), inspected November 17, 2026. The schematic and experiment code were authored independently for this demonstration. Sizes: input NMOS 8/0.15 µm, latch NMOS and PMOS 4/0.15 µm, tail 2/0.15 µm, precharge PMOS 1/0.15 µm. No upstream repository or PDK model source is vendored.
- [SKY130 PDK](https://github.com/google/skywater-pdk) and [open_pdks](https://github.com/fossi-foundation/open-pdks): separately installed model files and symbols, governed by their own notices/licenses. The project MIT license does not relicense them.
- [ngspice](https://ngspice.sourceforge.io/): separately installed simulator and shared library, governed by its own license notices. The ctypes declarations implement its published shared-library ABI.
- [Xschem](https://xschem.sourceforge.io/): optional schematic editor. The checked-in schematic references externally installed SKY130 symbols.
- [IIC-OSIC-TOOLS](https://github.com/iic-jku/IIC-OSIC-TOOLS): optional external EDA environment used for validation; not redistributed here.
- [Codex CLI](https://github.com/openai/codex): external model client. Hosted model service usage is subject to the user's account and service terms. No client binaries, authentication files or tokens are distributed.
- [Matplotlib](https://matplotlib.org/): optional plotting dependency, installed separately when requested.

`examples/recorded-session.json` is a sanitized historical recording, retaining numeric proposals and concise model-provided experiment explanations. It excludes original machine paths, session identifiers and raw client logs.
