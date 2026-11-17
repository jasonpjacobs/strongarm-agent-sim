# Installation and tool paths

Setup configures existing installations rather than downloading large EDA tools or PDKs automatically. This keeps model provenance explicit and avoids choosing a PDK revision for the user.

## ngspice

Install both the CLI and shared library. When compiling ngspice, the shared-library build uses `--with-ngshared`; use a separate build directory for the CLI. See the [official shared-library documentation](https://ngspice.sourceforge.io/shared.html), [manual](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf) and [downloads](https://ngspice.sourceforge.io/download.html). Point setup at the actual shared object, not a directory, executable or Python binding.

Example path patterns (installation-dependent):

- Linux executable: `/usr/bin/ngspice`; shared library: `/usr/lib/<architecture>/libngspice.so.0`.
- macOS: an executable under your package-manager prefix and `lib/libngspice.dylib` under the same installation.

The Python process and shared library must have the same architecture. An executable can work while loading its library fails because of missing dependent libraries or an ARM/x86 mismatch. `doctor` loads the library and checks the required API symbols before a simulation is launched.

The default solver setting is `sparse`. Use `--solver klu` only if your build includes KLU; the original experiment used ngspice 47 with KLU. The solver selection is included in replay provenance. The CLI's version and the shared library are separate checks: configuring one does not establish the version of the other.

## SKY130

Use a complete, ngspice-ready SKY130A installation built with [open_pdks](https://github.com/fossi-foundation/open-pdks), or the equivalent installation in your EDA environment. Set:

```sh
./setup.sh --sky130-lib /path/to/sky130A/libs.tech/ngspice/sky130.lib.spice \
  --ngspice /path/to/ngspice --ngspice-library /path/to/libngspice.so
```

Do not copy only `sky130.lib.spice`: it includes many other files. Setup recursively checks the include closure; runs record content hashes. The worker sets ngspice's `hsa` compatibility mode before loading the models. PDK-specific initialization files from other installations are isolated from the experiment.

Spaces in the repository and output paths are supported. Model paths are quoted in the SPICE deck; quote/newline characters in a model path are rejected. Setup exports configured executable directories in a local environment file, and all subprocesses use argument lists rather than shell interpolation.

## AI connection

Install and authenticate the [official Codex CLI](https://learn.chatgpt.com/docs/codex/cli). Configure `--codex` and `--model` during setup. The adapter uses the [structured-output CLI pattern](https://developers.openai.com/cookbook/examples/codex/build_iterative_repair_loops_with_codex), requires the flags checked by `doctor --ai`, and was tested originally with CLI 0.163.0. It deliberately does not read the user's general Codex configuration for plugins/tools; authentication still uses the normal Codex store.

`--model` must name a model available to your account. The historical model name in the example recording is not an access guarantee. Login is an explicit user step; setup and doctor never log in or request inference. No credential needs to be copied into this checkout.

## Optional isolated EDA environment

[IIC-OSIC-TOOLS](https://github.com/iic-jku/IIC-OSIC-TOOLS) provides an EDA image with ngspice and SKY130. For example, after obtaining a suitable image:

```sh
docker run --rm -it \
  --mount "type=bind,source=$PWD,target=/work" \
  --workdir /work --entrypoint /bin/bash \
  hpretl/iic-osic-tools:2026.10 -l

# Inside the container:
./setup.sh \
  --sky130-lib /foss/pdks/sky130A/libs.tech/ngspice/sky130.lib.spice \
  --ngspice /foss/tools/bin/ngspice \
  --ngspice-library /foss/tools/ngspice/lib/libngspice.so \
  --solver klu
./run.sh smoke
./run.sh recorded
```

Those are example **container** paths, not hardcoded runtime requirements. The tested ARM64 image digest is recorded in `validation.md`; users on other architectures should obtain the corresponding compatible image. The image is large and is not part of this source distribution.

For live AI in a container, Codex must be installed/authenticated **in that execution environment**, with network access to its provider. Alternatively, install the simulator and PDK locally and run the whole experiment on the host. This repository intentionally does not mount a host credential directory into a container automatically.

Local configuration records paths for the environment in which setup ran. Rerun setup when changing between host/container environments or moving the checkout. Config files and outputs are excluded from source archives.
