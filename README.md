# Actual Usage Evictor Journal Paper

This worktree contains the journal extraction for:

> **Implementation and Evaluation of an Actual-Usage Pre-Eviction Filter for
> Kubernetes Descheduler**

Authors: Matthew Hotmaraja Johan Turnip and Made Harta Dwijaksara.

The paper focuses exclusively on the Actual Usage Evictor and evaluates it
with the upstream `HighNodeUtilization` and `LowNodeUtilization` strategies.
Resource-defragmentation and network-aware contributions are intentionally
outside its scope.

## Build

```bash
latexmk -pdf -pdflatex="pdflatex -interaction=nonstopmode -halt-on-error" paper-actualusage.tex
```

The output is `paper-actualusage.pdf`. Use `latexmk -C
paper-actualusage.tex` to remove generated build files.

## Regenerate evaluation figures

The committed figures are reproducible from the experiment captures in the
sibling `descheduler-custom-real-usage-fixed` repository:

```bash
python3 scripts/generate_actual_usage_journal_figures.py
```

Override `--data-root` when the experiment repository is stored elsewhere.
The script writes:

- `assets/pics/actual-usage/failure_timeline_hnu_lnu.png`
- `assets/pics/actual-usage/availability_summary_hnu_lnu.png`

## Source organization

- `paper-actualusage.tex`: journal entry point and formatting;
- `src/paper-actualusage/`: article sections;
- `assets/codes/figures/`: vector workflow figure;
- `assets/codes/pseudos/actualusage/`: algorithm and example configuration;
- `config/references.bib`: shared bibliography.

The original `thesis.tex` and thesis chapters are retained as source material
and are not included by the journal entry point.
