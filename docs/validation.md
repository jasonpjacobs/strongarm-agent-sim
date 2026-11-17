# Validation record

Validated November 17, 2026.

## Standalone distribution

The new checkout was copied into a disposable Linux ARM64 container with network access disabled. The test used only this repository plus externally installed EDA tools/PDK. It did not access the original experiment directory, an existing named container, credentials or a model service.

| Check | Result |
| --- | --- |
| Python unit tests | 17 passed (macOS host and Linux container) |
| Setup/doctor | CLI, shared-library entry points and 319 recursively included model files verified |
| Functional smoke | 10 trial decisions passed; reset, actual input, retained rails and synchronization checked |
| Smoke exact replay | 40,483 accepted samples and all observations matched |
| Recorded AI actions, KLU | All 12 recorded decision polarities reproduced |
| KLU exact replay | 48,603 accepted samples and all observations matched |
| Relocated checkout | Setup rerun from another directory; 48,603 replay samples still matched |
| Paths with spaces | Checkout and smoke-output paths included spaces |
| Default Sparse solver | All 12 recorded decisions reproduced; 48,603 samples matched local replay |
| Live AI preflight | Initial paused observation and prepared prompt generated; zero model calls |
| Model adapter unit test | Configured CLI path, structured response, disabled tools and exact voltage transport verified with a test subprocess substitute |

The portability test exposed ngspice's interactive `source` command mishandling quoted paths with spaces. The packaged worker now loads the circuit through `ngSpice_Circ` instead. Tests were rerun after this change.

The original live AI integration had already been exercised with 13 real model calls and exact replay. Packaging validation did not make additional paid inference calls. Native macOS Python unit tests pass; full native macOS ngspice execution and native Windows execution were not tested. Windows users should use Linux/WSL.

## EDA environment used

- Python 3.12.3 in the Linux container; Python 3.12 on the macOS host.
- ngspice 47; shared library built October 15, 2026, with KLU available.
- SKY130A TT; 27 °C.
- open_pdks revision `1689ac3f2dc763876eaf967227c7dfe831b031ae` from the original environment record.
- IIC-OSIC-TOOLS image `hpretl/iic-osic-tools:2026.10`, ARM64 image digest `sha256:306585de35d198e70ea58950f77147c86f56c698726a19afea9f1c83009557be`.

The image digest is an ARM64 reference, not an instruction to use an incompatible architecture. Each new run records actual library, model, circuit and worker hashes and numerical settings in its own manifest. Fresh runs on other builds must establish their own local replay baseline.

## Test coverage

Unit tests reject stale evidence, invalid/nonfinite amplitudes, fabricated bracket endpoints and missing references to the latest observation. They check that the offset/internal-input fields are excluded from model contexts and that a non-midpoint model choice is preserved exactly. Measurement tests reject incomplete precharge, wrong applied stimuli, unresolved outputs and brief output glitches. Portability tests cover recursive include hashing, missing include detection, canonical netlist identity after changing the PDK path and sanitized recording contents.

The integration smoke test additionally exercises request idempotency, stale/conflicting requests, no state change on rejection, and wall-clock isolation. Actual experiment/replay comparisons require identical full observations and accepted waveform history, not merely similar plots or matching final voltages.

## Static explainer

The GitHub Pages site was checked in a browser at desktop and 390 px mobile widths, served from a `/docs/` subpath. Verification covered selecting numbered decisions and plotted stems, full-run/cycle/decision-edge views, expandable response JSON, the final stop call, and downloading the dataset. The mobile page had no horizontal overflow; browser checks reported no JavaScript errors. OUTN uses 40% transparency (60% opacity).

The Python suite now has **20 passing tests on the macOS host**. Three added data checks compare every published response and polarity with the portable recording, verify all 48,603 samples and applied amplitudes, and check that private metadata is excluded. The site JavaScript also passes `node --check`. This website work made no new inference calls and did not change simulator code.
