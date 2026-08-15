# Building the RingSentry JOSS paper

The submission source is `paper.md`; references are in `paper.bib`, and
figures are under `figures/`.

JOSS's current official local build uses Inara:

```bash
docker run --rm \
  --volume "$PWD/paper:/data" \
  --env JOURNAL=joss \
  openjournals/inara
```

The repository also contains
`.github/workflows/draft-pdf.yml`, which uses the official
`openjournals/openjournals-draft-action` and uploads `paper.pdf` as a
workflow artifact. Generated PDF and intermediate files are ignored by Git.

Regenerate the editable figure sources and all submission exports from the
repository root with:

```bash
python paper/figures/make_figures.py \
  --output-dir paper/figures \
  --formats svg pdf png
```

Run the manuscript-facing consistency checks with:

```bash
python -m pytest -q \
  tests/test_documentation_links.py \
  tests/test_metadata_consistency.py
```

Before submission, replace the evidence-limited text in the Research impact,
Acknowledgements, AI usage, and contributions/competing-interests sections only
with author-confirmed facts. Re-run the official build and reference checks
after every metadata or bibliography change.
