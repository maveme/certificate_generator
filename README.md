# ICSA 2026 Certificate Generator

Generates one PDF attendance certificate per participant by substituting names into a LaTeX template and compiling with `pdflatex`.

---

## Directory layout

```
script/
├── generate_certificates.py   # main script
├── Badges.csv                 # participant list
├── latex_template/
│   ├── certificate.tex        # LaTeX template (contains FULL-NAME placeholder)
│   └── ICSA26_Logo.jpg        # logo image referenced by the template
└── output/                    # generated PDFs land here (created automatically)
```

---

## Requirements

### Python
Python 3.6 or later. No third-party packages — only the standard library is used.

### pdflatex

| Platform | Install |
|----------|---------|
| macOS    | [MacTeX](https://www.tug.org/mactex/) — `brew install --cask mactex` |
| Linux    | `sudo apt install texlive-full` (Debian/Ubuntu) |
| Windows  | [MiKTeX](https://miktex.org/) or [TeX Live](https://www.tug.org/texlive/) |

Verify the install: `pdflatex --version`

---

## Usage

```bash
python3 generate_certificates.py
```

PDFs are written to `output/` in the same directory as the script. The folder is created automatically if it does not exist.

---

## How it works

### 1. Pre-flight checks
Before touching any files the script verifies that:
- `latex_template/` directory exists
- `latex_template/certificate.tex` exists and contains the `FULL-NAME` placeholder
- `Badges.csv` exists and has a `Full Name` column
- `pdflatex` is on the system PATH

Any missing item exits immediately with a clear error message.

### 2. Reading participants
`Badges.csv` is read with Python's built-in `csv.DictReader`. Each value in the `Full Name` column is normalised with `" ".join(name.split())`, which collapses stray tabs and multiple spaces that Excel can introduce when exporting CSVs.

### 3. LaTeX special-character escaping
Names are passed through `escape_latex()` before being inserted into the template. This function replaces the ten LaTeX special characters (`\ & % $ # _ { } ~ ^`) with their safe equivalents, preventing compilation errors for names that contain any of them. The backslash is escaped first to avoid double-escaping.

### 4. Per-participant compilation
For each participant:

1. The template text is loaded and `FULL-NAME` is replaced with the escaped name.
2. The modified source is written to a temporary `.tex` file inside a `tempfile.TemporaryDirectory`.
3. `pdflatex` is invoked via `subprocess.run` with:
   - `-interaction=nonstopmode` — don't pause on minor warnings.
   - `-halt-on-error` — exit with a non-zero code on fatal errors.
   - `-output-directory` pointing at the temp directory so auxiliary files (`.aux`, `.log`) never reach the project tree.
   - `TEXINPUTS` environment variable set to `latex_template/` so the logo image is found regardless of working directory.
4. The compiled PDF is moved from the temp directory to `output/<Name>.pdf`.
5. The temp directory (and all auxiliary files) is deleted automatically when the `with` block exits.

### 5. Error handling
- A `pdflatex` failure for one participant prints the last 20 lines of the compiler log and continues to the next name — one bad name cannot abort the whole batch.
- `pdflatex` output is captured as raw bytes and decoded with `errors="replace"` so names containing diacritics (e.g. "Cernău") do not cause a `UnicodeDecodeError` in the logging path.
- A missing `pdflatex` binary produces a hard exit with platform-specific install instructions.

### 6. Summary
After the loop, the script prints the count of successes and failures.

---

## Customising the template

- **Placeholder**: The script looks for the literal string `FULL-NAME` in `certificate.tex`. Rename it in both files if you want a different token.
- **Logo or layout**: Edit `certificate.tex` freely; the script re-reads it from disk on every run.
- **Output directory**: Change the `OUTPUT_DIR` constant at the top of `generate_certificates.py`.
- **CSV column name**: Change the `NAME_COLUMN` constant if your spreadsheet uses a different header.
