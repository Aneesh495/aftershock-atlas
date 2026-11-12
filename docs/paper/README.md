# Offline thesis

The [PDF thesis](aftershock-thesis.pdf) renders the [thesis Markdown](../THESIS.md) and the frozen public historical score partition. The coverage figure's eighteen underlying values are preserved in [CSV](historical-coverage.csv); the editable vector figure is [SVG](historical-coverage.svg). [Artifact identities](ARTIFACT.json) bind the PDF to its source, public score bytes, figure data and authoring code. This is document rendering, not model fitting or independent scientific verification.

```sh
uv run --with-requirements docs/paper/requirements.txt python docs/paper/build_thesis.py --publication-source 0a5657fce0d854d844706c7b7a1bd088f22156e0
mkdir -p .agent-local/paper-qa
pdftoppm -r 100 -png docs/paper/aftershock-thesis.pdf .agent-local/paper-qa/page
```

Use an accounted project temporary path for rendering in a bounded research campaign. Inspect every rendered page before distributing the PDF. The scientific executable remains 1bd53f80841fe08c1bfd3a2fafb9c8d53b042cb0. The publication source names the documented snapshot; it does not claim that the PDF authoring utility was part of that scientific runtime.
