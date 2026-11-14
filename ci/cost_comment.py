"""Ends the PR's summary comment with the review cost (the review workflow inlines this file, engine-neutral).

The Cost step writes one line per transcript, "<stage> <usd>", to a parts file. This module turns those lines into a
single "Review cost" line under MARK, after the summary body. A later call replaces that line, so an incremental push
leaves one cost line, the newer one. Standard library only.
"""
import argparse
import math
import sys
from pathlib import Path

MARK = "<!-- pr-review:cost -->"


def read_parts(text):
    """Parse "<stage> <usd>" lines; blank, unparsable, negative and non-finite (nan, inf) lines are skipped. Returns [(stage, usd)] in the given order."""
    parts = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) != 2:
            continue
        try:
            usd = float(fields[1])
        except ValueError:
            continue
        if math.isfinite(usd) and usd >= 0:
            parts.append((fields[0], usd))
    return parts


def format_line(parts):
    if not parts:
        return "Review cost: not recorded for this run"
    total = sum(usd for _, usd in parts)
    detail = ", ".join(f"{stage} ${usd:.3f}" for stage, usd in parts)
    return f"Review cost: ${total:.4f} ({detail})"


def with_cost(body, line):
    """The body without any earlier cost line (everything from MARK on), then the cost line under MARK."""
    head = body.split(MARK, 1)[0].rstrip()
    return f"{head}\n\n{MARK}\n{line}\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Print the summary comment body with the review cost line.")
    ap.add_argument("--body-file", required=True)
    ap.add_argument("--parts-file", required=True)
    args = ap.parse_args(argv)
    body = Path(args.body_file).read_text(encoding="utf-8")
    parts_path = Path(args.parts_file)
    parts = read_parts(parts_path.read_text(encoding="utf-8")) if parts_path.is_file() else []
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(with_cost(body, format_line(parts)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
