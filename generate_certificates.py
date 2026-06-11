#!/usr/bin/env python3
"""
generate_certificates.py

Generates one PDF certificate per participant by substituting each name
into a LaTeX template and compiling with pdflatex.

Usage:
    python generate_certificates.py

Dependencies:
    - pdflatex (part of MacTeX on macOS: https://www.tug.org/mactex/
      or TeX Live on Linux: sudo apt install texlive-full)
    - Python 3.6+ (no third-party packages required)
"""

import csv
import os
import re
import shutil
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "latex_template")
TEMPLATE_FILE = os.path.join(TEMPLATE_DIR, "certificate.tex")
CSV_FILE = os.path.join(os.path.dirname(__file__), "Badges.csv")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
PLACEHOLDER = "FULL-NAME"
NAME_COLUMN = "Full Name"

# pdflatex is called twice so cross-references resolve, but this template
# has none — one pass is enough.
PDFLATEX_PASSES = 1

# ---------------------------------------------------------------------------
# LaTeX escaping
# ---------------------------------------------------------------------------

# Characters that carry special meaning in LaTeX and must be escaped.
# Order matters: backslash must come first to avoid double-escaping.
_LATEX_ESCAPE_MAP = [
    ("\\", r"\textbackslash{}"),
    ("&",  r"\&"),
    ("%",  r"\%"),
    ("$",  r"\$"),
    ("#",  r"\#"),
    ("_",  r"\_"),
    ("{",  r"\{"),
    ("}",  r"\}"),
    ("~",  r"\textasciitilde{}"),
    ("^",  r"\textasciicircum{}"),
]


def escape_latex(text: str) -> str:
    """Return *text* with all LaTeX special characters safely escaped."""
    for char, replacement in _LATEX_ESCAPE_MAP:
        text = text.replace(char, replacement)
    return text


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

def sanitize_filename(name: str) -> str:
    """Strip characters that are unsafe in filenames (keep letters, digits, spaces, hyphens)."""
    return re.sub(r'[^\w\s\-]', '', name).strip()


def compile_certificate(name: str, template_content: str) -> bool:
    """
    Substitute *name* into *template_content*, write a temporary .tex file,
    compile it with pdflatex, and place the resulting PDF in OUTPUT_DIR.

    Returns True on success, False on failure.
    """
    escaped_name = escape_latex(name)
    tex_source = template_content.replace(PLACEHOLDER, escaped_name)

    safe_name = sanitize_filename(name)
    if not safe_name:
        print(f"  [SKIP] Name '{name}' produces an empty filename — skipping.")
        return False

    # Work inside a temp directory so auxiliary files never pollute the tree.
    with tempfile.TemporaryDirectory() as tmp_dir:
        tex_path = os.path.join(tmp_dir, f"{safe_name}.tex")

        with open(tex_path, "w", encoding="utf-8") as fh:
            fh.write(tex_source)

        # pdflatex needs the template assets (logo image, etc.) to be reachable.
        # Passing -output-directory keeps all generated files in tmp_dir;
        # TEXINPUTS lets pdflatex find files in the original template folder.
        env = os.environ.copy()
        env["TEXINPUTS"] = TEMPLATE_DIR + os.pathsep + env.get("TEXINPUTS", "")

        cmd = [
            "pdflatex",
            "-interaction=nonstopmode",   # don't halt on minor errors
            "-halt-on-error",             # but do exit non-zero on fatal ones
            f"-output-directory={tmp_dir}",
            tex_path,
        ]

        for pass_num in range(1, PDFLATEX_PASSES + 1):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,   # capture raw bytes
                    env=env,
                )
            except FileNotFoundError:
                print(
                    "\n[FATAL] pdflatex not found. "
                    "Install MacTeX (macOS) or TeX Live (Linux) and ensure it is on PATH.\n"
                )
                sys.exit(1)

            if result.returncode != 0:
                print(f"  [ERROR] pdflatex failed for '{name}' (pass {pass_num}).")
                # Decode leniently — pdflatex output may mix encodings.
                log_text = result.stdout.decode("utf-8", errors="replace")
                log_tail = "\n".join(log_text.splitlines()[-20:])
                print(f"  --- pdflatex output ---\n{log_tail}\n  -----------------------")
                return False

        # Move the compiled PDF out of the temp dir into OUTPUT_DIR.
        compiled_pdf = os.path.join(tmp_dir, f"{safe_name}.pdf")
        dest_pdf = os.path.join(OUTPUT_DIR, f"{safe_name}.pdf")

        if not os.path.isfile(compiled_pdf):
            print(f"  [ERROR] pdflatex reported success but PDF not found for '{name}'.")
            return False

        shutil.move(compiled_pdf, dest_pdf)

    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # --- Pre-flight checks --------------------------------------------------

    if not os.path.isdir(TEMPLATE_DIR):
        sys.exit(f"[FATAL] Template directory not found: {TEMPLATE_DIR}")

    if not os.path.isfile(TEMPLATE_FILE):
        sys.exit(f"[FATAL] Template file not found: {TEMPLATE_FILE}")

    if not os.path.isfile(CSV_FILE):
        sys.exit(f"[FATAL] CSV file not found: {CSV_FILE}")

    if shutil.which("pdflatex") is None:
        sys.exit(
            "[FATAL] pdflatex is not on PATH.\n"
            "  macOS : install MacTeX from https://www.tug.org/mactex/\n"
            "  Linux : sudo apt install texlive-full  (or equivalent)\n"
        )

    # --- Load resources -----------------------------------------------------

    with open(TEMPLATE_FILE, "r", encoding="utf-8") as fh:
        template_content = fh.read()

    if PLACEHOLDER not in template_content:
        sys.exit(
            f"[FATAL] Placeholder '{PLACEHOLDER}' not found in template. "
            "Nothing to substitute."
        )

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # --- Read participants ---------------------------------------------------

    participants: list[str] = []
    with open(CSV_FILE, newline="", encoding="utf-8-sig") as fh:
        # utf-8-sig strips a leading BOM that Excel sometimes adds.
        reader = csv.DictReader(fh)

        if NAME_COLUMN not in (reader.fieldnames or []):
            sys.exit(
                f"[FATAL] Column '{NAME_COLUMN}' not found in CSV. "
                f"Available columns: {reader.fieldnames}"
            )

        for row in reader:
            # Split on any whitespace (handles stray tabs from Excel exports)
            # then rejoin with a single space.
            name = " ".join(row[NAME_COLUMN].split())
            if name:
                participants.append(name)

    if not participants:
        sys.exit("[FATAL] No participant names found in the CSV file.")

    print(f"Found {len(participants)} participant(s). Generating certificates...\n")

    # --- Generate certificates ----------------------------------------------

    success_count = 0
    failure_count = 0

    for i, name in enumerate(participants, start=1):
        print(f"[{i:>4}/{len(participants)}] {name} ...", end=" ", flush=True)
        ok = compile_certificate(name, template_content)
        if ok:
            print("OK")
            success_count += 1
        else:
            failure_count += 1

    # --- Summary ------------------------------------------------------------

    print(f"\nDone. {success_count} certificate(s) generated in '{OUTPUT_DIR}'.")
    if failure_count:
        print(f"       {failure_count} certificate(s) failed — see errors above.")


if __name__ == "__main__":
    main()
