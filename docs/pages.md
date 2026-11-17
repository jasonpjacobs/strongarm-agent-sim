# Host the interactive explainer

The static site starts at `docs/index.html`. It includes the original measured waveforms, an interactive stem plot of the AI-selected differential input, and expandable model responses for all 12 experiments plus the final stop call. The +43 mV fixed series offset is labeled separately from the model-controlled stimulus.

Published demonstration: [www.jasonjacobs.net/strongarm-agent-sim](https://www.jasonjacobs.net/strongarm-agent-sim/). Source: [jasonpjacobs/strongarm-agent-sim](https://github.com/jasonpjacobs/strongarm-agent-sim).

## Preview locally

Open `docs/index.html` in a browser. All assets are local; no simulator, PDK, model account, Node installation or build step is required. Alternatively, from the repository root:

```sh
python3 -m http.server 8000 --bind 127.0.0.1
# Open http://127.0.0.1:8000/docs/
```

Select a numbered button or a stem to choose an experiment. The response panel shows the model's original explanation, expected observation, cited evidence and expandable JSON. Its measurements and bracket show what was learned **after** that trial. The JSON's threshold estimates belong to the model's **pre-trial** response. The stop call at 240 ns applies no stimulus.

The waveform buttons switch between the full 240 ns run, the selected 20 ns cycle, and its clock-rise/regeneration interval. Hover over either chart for numerical values. All decisions are also selectable using keyboard-accessible buttons; the response panel supplies the selected numeric measurements without relying on color or the canvas. A download button saves the dataset as JSON.

## Publish with GitHub Pages

1. Push this repository and its `docs` folder to GitHub.
2. Open **Settings → Pages → Build and deployment**.
3. Choose **Deploy from a branch**, select the branch containing these files, and choose **`/docs`** as the folder. Save.
4. Open the Pages URL GitHub reports after deployment completes.

See GitHub's [publishing-source documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site). The site uses relative asset URLs, so it works at a project URL such as `https://YOUR_NAME.github.io/YOUR_REPOSITORY/` as well as at a custom-domain root. `docs/.nojekyll` requests static serving. No workflow, API token, CDN, analytics or external fonts are needed. Markdown guide links open the source text; GitHub Pages does not render those files when Jekyll is disabled.

Only publish `docs/`. Local configuration, credentials, PDK files and private run directories do not belong in the site. The checked-in dataset was exported through an explicit allowlist.

## Where the data comes from

`assets/experiment.js` contains the original model-controlled run from November 17, 2026, not a reconstruction using a scripted policy. It includes:

- All **48,603 accepted timepoints**: time, clock, OUTP, OUTN and external differential input.
- All 12 model trial responses, the final stop response, observed outputs and inference durations.
- The verified replay result and SHA-256 hashes identifying the original waveform and verification files.

The export excludes internal input nodes, credentials, machine paths, service session identifiers, raw CLI logs, netlists and PDK files. The fixed synthetic offset is disclosed to readers of this explainer; it was hidden from the model during the recorded run. Provenance hashes identify source files but are not a service attestation.

The browser dataset rounds time to 1e-9 ns, voltages to 1e-7 V and external differential input to 1e-7 mV. Replay was verified against the original full-precision data, **before** display rounding. The plots retain each display pixel's first, last, minimum and maximum values in time order, preserving narrow pulses. Full-window measurements are exported from the original data rather than recomputed from rendered lines.

## Refreshing the demonstration

With a completed, successfully verified AI run available locally:

```sh
python3 scripts/export_explainer.py --run runs/live-demo
```

The export requires `verification.json`, `live/manifest.json`, `live/waveforms.jsonl` and the final `call-*/timing.json`. The script checks run/replay success and the accepted sample count. It creates the dataset consumed by the page without copying the private source files. Do not run fresh inference just to build the website.

The narrative, conditions, result summary and counts in `index.html` describe the original fixture and run. If replacing its dataset, update that prose to match the new experiment, including any changed fixed offset, clock timing or circuit conditions. The chart's reset and decision-edge windows also assume this experiment's 20 ns cycle. Keep `examples/recorded-session.json` aligned if replacing the published demonstration, then run:

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
node --check docs/assets/explainer.js  # optional developer syntax check
```
