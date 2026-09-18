"""
Build notebooks from the analysis scripts.

The scripts in analysis/ are written in "percent" format: every cell begins
with a line that is either `# %%` (code) or `# %% [markdown]` (text). This
tool splits each script on those markers, writes a .ipynb into notebooks/,
then executes it so the outputs are stored inline.

Run from the project root:  python tools/make_notebooks.py
The notebooks are a view of the scripts. Edit the script, rerun this. Never
edit a notebook by hand and expect the script to follow.
"""

import re
import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = sorted((ROOT / "analysis").glob("0*_*.py"))
OUT_DIR = ROOT / "notebooks"
CELL_RE = re.compile(r"^# %%( \[markdown\])?\s*$")


def split_cells(text):
    cells = []
    kind, buf = None, []
    for line in text.splitlines():
        m = CELL_RE.match(line)
        if m:
            if kind is not None:
                cells.append((kind, "\n".join(buf).strip("\n")))
            kind = "markdown" if m.group(1) else "code"
            buf = []
        else:
            buf.append(line)
    if kind is not None:
        cells.append((kind, "\n".join(buf).strip("\n")))
    return cells


def to_notebook(cells):
    nb = nbformat.v4.new_notebook()
    for kind, body in cells:
        if not body.strip():
            continue
        if kind == "markdown":
            # strip the leading "# " that keeps the text a Python comment in the script
            md = "\n".join(l[2:] if l.startswith("# ") else l.lstrip("#") for l in body.splitlines())
            nb.cells.append(nbformat.v4.new_markdown_cell(md))
        else:
            nb.cells.append(nbformat.v4.new_code_cell(body))
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    return nb


def main():
    OUT_DIR.mkdir(exist_ok=True)
    for script in SCRIPTS:
        cells = split_cells(script.read_text(encoding="utf-8"))
        nb = to_notebook(cells)
        target = OUT_DIR / (script.stem + ".ipynb")
        print(f"{script.name}: {len(nb.cells)} cells, executing ...", flush=True)
        # cwd=ROOT so the relative data/ and outputs/ paths inside the cells resolve
        client = NotebookClient(nb, timeout=600, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}})
        client.execute()
        nbformat.write(nb, target)
        print(f"  wrote {target.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
