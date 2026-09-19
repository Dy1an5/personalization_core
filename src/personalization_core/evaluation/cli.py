"""Command line entry point for deterministic evaluation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from .report import render_json, render_markdown
from .runner import load_dataset, run_evaluation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic Core evaluations")
    parser.add_argument(
        "--dataset",
        type=Path,
        help="JSON dataset file or directory containing minimal.json",
    )
    parser.add_argument("--json-out", type=Path, help="Write JSON report to this path")
    parser.add_argument(
        "--markdown-out", type=Path, help="Write Markdown report to this path"
    )
    return parser


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        dataset = load_dataset(args.dataset)
        report = run_evaluation(
            dataset,
            dataset_name=(args.dataset.stem if args.dataset else "minimal"),
        )
    except (OSError, ValueError, ValidationError) as exc:
        print(f"evaluation input error: {exc}", file=sys.stderr)
        return 2

    json_report = render_json(report)
    markdown_report = render_markdown(report)
    if args.json_out is not None:
        _write(args.json_out, json_report)
    else:
        sys.stdout.write(json_report)
    if args.markdown_out is not None:
        _write(args.markdown_out, markdown_report)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
