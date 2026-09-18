# Olist business analysis, Zain hackathon

Three quantified business problems with recommendations, built on the Olist
Brazilian e-commerce dataset. Python and Polars throughout, scipy for
confidence intervals, matplotlib for figures. No database.

## Start here

1. `docs/FINDINGS.md` has every result and where it came from.
2. `docs/ANALYSIS_DECISIONS.md` has every judgement call and its alternative.
3. `docs/CODE_WALKTHROUGH.md` explains every line of the analysis.
4. `docs/JUDGE_QUESTIONS.md` is the likely questions with answers.
5. `docs/REPORT_GUIDE.md` is what goes in the report, deck, and dashboard.
6. `docs/SCHEMA.md` is the dataset, table by table.

## Layout

```
olist-zain/
  data/
    raw/          the nine Olist CSVs. Empty in the repo; drop them in.
    cleaned/      the twelve cleaned CSVs. Empty in the repo; drop them in.
  cleaning/
    clean.py              produces data/cleaned/ from data/raw/
    verify_cleaning.py    49 checks on the cleaned files
    decisions.md          every cleaning choice with its count
  analysis/
    01_delivery.py        scenario 1
    02_sellers.py         scenario 2
    03_freight.py         scenario 3
  notebooks/
    01_delivery.ipynb     same code as the scripts, with outputs inline
    02_sellers.ipynb
    03_freight.ipynb
  verify/
    verify_results.py     recomputes every headline with plain Python, no Polars
  outputs/
    exports/              CSVs for the dashboard. Column names are the contract.
    figures/              PNGs for the report
  docs/                   see "Start here"
  tools/
    make_notebooks.py     rebuilds the notebooks from the scripts
  run_all.py              runs everything in order
  requirements.txt
```

## Setup

```
pip install -r requirements.txt
```

Put the nine raw CSVs in `data/raw/` and the twelve cleaned CSVs in
`data/cleaned/`. If you only have the raw files, run `python cleaning/clean.py`
from the project root to produce the cleaned ones.

## Run

Everything runs from the project root, because paths inside the scripts are
relative to it.

```
python run_all.py
```

That runs the cleaning check, the three analyses, the results verification,
and rebuilds the notebooks. About two minutes. Add `--skip-notebooks` to
leave the notebooks out.

Or one at a time:

```
python cleaning/verify_cleaning.py
python analysis/01_delivery.py
python analysis/02_sellers.py
python analysis/03_freight.py
python verify/verify_results.py
python tools/make_notebooks.py
```

## Scripts and notebooks

The scripts in `analysis/` are the source. The notebooks are generated from
them. If you change a script, run `python tools/make_notebooks.py` to
regenerate. Do not edit a notebook by hand and expect the script to follow.

## Verifying the numbers

Two independent checks:

- `cleaning/verify_cleaning.py` confirms the cleaned files are what
  `cleaning/decisions.md` says they are.
- `verify/verify_results.py` recomputes every exported headline number
  using only Python's csv module and loops, then compares. It exits non-zero
  on any mismatch.

Both pass on the current data. If you change a threshold in a script
(`MIN_REVIEWED_ORDERS`, `WORST_N`, `MIN_ITEMS_PER_GROUP`), rerun the analysis
and the verification will tell you whether the exports still match.

## Attribution

Olist Brazilian E-Commerce Public Dataset, Kaggle, CC BY-NC-SA 4.0.
Non-commercial licence: this analysis is a demonstration and the raw data
is not for commercial reuse.

## A note on the cleaning scripts

`cleaning/clean.py` and `cleaning/verify_cleaning.py` are written in pandas.
They were built before the decision to use Polars for the project, and they
have been verified, so they were kept as-is. Everything in `analysis/` and
`verify/` is Polars or plain Python. If the cleaning needs to be Polars too,
say so and it can be ported.
