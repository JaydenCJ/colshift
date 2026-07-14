"""The colshift command line: ``compare`` and ``profile``.

Exit codes:
  0 — success (and, for compare, drift below the --fail-on gate)
  1 — compare found drift at or above the --fail-on level
  2 — usage error, unreadable input, or invalid profile
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import FrozenSet, List, Optional, Sequence

from . import __version__
from .drift import ALERT, OK, WARN, Thresholds, compare
from .errors import ColshiftError, InputError, ProfileError
from .inference import DEFAULT_NULL_TOKENS
from .loaders import Dataset, load_table
from .profiles import (
    DEFAULT_BINS,
    DEFAULT_TOP_K,
    DatasetProfile,
    profile_dataset,
    profile_from_dict,
    profile_to_dict,
)
from .report import render_json, render_markdown

_FAIL_RANK = {WARN: 1, ALERT: 2}
_VERDICT_RANK = {OK: 0, WARN: 1, ALERT: 2}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="colshift",
        description="Report per-column distribution drift between two dataset snapshots: "
        "PSI, ranges, null rates.",
    )
    parser.add_argument("--version", action="version", version=f"colshift {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    cmp_parser = subparsers.add_parser(
        "compare",
        help="compare a current snapshot against a baseline (raw data or stored profile)",
        description="Compare CURRENT against BASELINE and emit a drift report. BASELINE may be "
        "raw data (.csv/.tsv/.jsonl) or a profile JSON written by 'colshift profile'; "
        "CURRENT must be raw data.",
    )
    cmp_parser.add_argument("baseline", help="baseline snapshot (.csv/.tsv/.jsonl) or profile (.json)")
    cmp_parser.add_argument("current", help="current snapshot (.csv/.tsv/.jsonl)")
    cmp_parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="report format for stdout or --out (default: markdown)",
    )
    cmp_parser.add_argument("--out", metavar="FILE", help="write the report to FILE instead of stdout")
    cmp_parser.add_argument(
        "--json-out",
        metavar="FILE",
        help="additionally write the JSON report to FILE (regardless of --format)",
    )
    cmp_parser.add_argument(
        "--columns",
        metavar="A,B,C",
        help="compare only these columns (comma-separated)",
    )
    cmp_parser.add_argument(
        "--exclude",
        metavar="A,B,C",
        help="skip these columns (comma-separated; unknown names are ignored)",
    )
    cmp_parser.add_argument(
        "--psi-warn", type=float, default=Thresholds.psi_warn, metavar="X",
        help="PSI warn threshold (default: %(default)s)",
    )
    cmp_parser.add_argument(
        "--psi-alert", type=float, default=Thresholds.psi_alert, metavar="X",
        help="PSI alert threshold (default: %(default)s)",
    )
    cmp_parser.add_argument(
        "--null-warn", type=float, default=Thresholds.null_warn, metavar="X",
        help="null-rate delta warn threshold, absolute 0..1 (default: %(default)s)",
    )
    cmp_parser.add_argument(
        "--null-alert", type=float, default=Thresholds.null_alert, metavar="X",
        help="null-rate delta alert threshold, absolute 0..1 (default: %(default)s)",
    )
    cmp_parser.add_argument(
        "--fail-on",
        choices=["never", "warn", "alert"],
        default="alert",
        help="exit 1 when the overall verdict reaches this level (default: alert)",
    )
    _add_input_options(cmp_parser, for_compare=True)
    cmp_parser.set_defaults(func=cmd_compare)

    prof_parser = subparsers.add_parser(
        "profile",
        help="summarize one snapshot into a committable profile JSON",
        description="Profile INPUT into a compact JSON summary (quantile bins, top-K categories, "
        "null rates) usable later as a compare baseline — no raw rows are stored.",
    )
    prof_parser.add_argument("input", help="snapshot to profile (.csv/.tsv/.jsonl)")
    prof_parser.add_argument("--out", "-o", metavar="FILE", help="write the profile to FILE (default: stdout)")
    _add_input_options(prof_parser, for_compare=False)
    prof_parser.set_defaults(func=cmd_profile)

    return parser


def _add_input_options(parser: argparse.ArgumentParser, for_compare: bool) -> None:
    profile_note = "; ignored when the baseline is a stored profile" if for_compare else ""
    parser.add_argument(
        "--bins", type=int, default=DEFAULT_BINS, metavar="N",
        help=f"quantile buckets for numeric PSI, 2-1000 (default: %(default)s{profile_note})",
    )
    parser.add_argument(
        "--top-k", type=int, default=DEFAULT_TOP_K, metavar="N",
        help=f"categories stored per categorical column (default: %(default)s{profile_note})",
    )
    parser.add_argument(
        "--null-tokens",
        metavar="A,B,C",
        help="comma-separated tokens treated as null, replacing the default set "
        "(empty/whitespace-only cells are always null)",
    )
    parser.add_argument(
        "--delimiter",
        metavar="CHAR",
        help="field delimiter for delimited files (default: ',' for .csv, tab for .tsv)",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse handles --help/--version/usage errors
        return int(exc.code or 0)
    try:
        return int(args.func(args))
    except ColshiftError as exc:
        print(f"colshift: error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"colshift: error: {exc}", file=sys.stderr)
        return 2


def cmd_compare(args: argparse.Namespace) -> int:
    _validate_common(args)
    null_tokens = _parse_null_tokens(args.null_tokens)
    thresholds = Thresholds(
        psi_warn=args.psi_warn,
        psi_alert=args.psi_alert,
        null_warn=args.null_warn,
        null_alert=args.null_alert,
    )
    if args.psi_warn < 0 or args.null_warn < 0:
        raise InputError("warn thresholds must be >= 0")
    if args.psi_alert < args.psi_warn or args.null_alert < args.null_warn:
        raise InputError("alert thresholds must be >= their warn thresholds")

    baseline_path = Path(args.baseline)
    if baseline_path.suffix.lower() == ".json":
        baseline = _load_profile_file(baseline_path)
    else:
        baseline_ds = load_table(baseline_path, delimiter=args.delimiter)
        baseline = profile_dataset(
            baseline_ds, bins=args.bins, top_k=args.top_k, null_tokens=null_tokens
        )

    current_path = Path(args.current)
    if current_path.suffix.lower() == ".json":
        raise InputError(
            "the current snapshot must be raw data (.csv/.tsv/.jsonl); "
            "only the baseline may be a stored profile"
        )
    current = load_table(current_path, delimiter=args.delimiter)

    include = _parse_names(args.columns)
    exclude = _parse_names(args.exclude)
    baseline, current = _apply_column_filters(baseline, current, include, exclude)

    report = compare(
        baseline,
        current,
        thresholds=thresholds,
        null_tokens=null_tokens,
        baseline_source=str(baseline_path),
    )

    text = render_json(report) if args.format == "json" else render_markdown(report)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"report written to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    if args.json_out:
        Path(args.json_out).write_text(render_json(report), encoding="utf-8")
        print(f"JSON report written to {args.json_out}", file=sys.stderr)

    if args.fail_on == "never":
        return 0
    return 1 if _VERDICT_RANK[report.verdict] >= _FAIL_RANK[args.fail_on] else 0


def cmd_profile(args: argparse.Namespace) -> int:
    _validate_common(args)
    null_tokens = _parse_null_tokens(args.null_tokens)
    dataset = load_table(Path(args.input), delimiter=args.delimiter)
    profile = profile_dataset(dataset, bins=args.bins, top_k=args.top_k, null_tokens=null_tokens)
    text = json.dumps(profile_to_dict(profile), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"profile written to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


def _validate_common(args: argparse.Namespace) -> None:
    if not 2 <= args.bins <= 1000:
        raise InputError(f"--bins must be between 2 and 1000, got {args.bins}")
    if not 1 <= args.top_k <= 10000:
        raise InputError(f"--top-k must be between 1 and 10000, got {args.top_k}")
    if args.delimiter is not None and len(args.delimiter) != 1:
        raise InputError("--delimiter must be a single character")


def _parse_null_tokens(spec: Optional[str]) -> FrozenSet[str]:
    if spec is None:
        return DEFAULT_NULL_TOKENS
    return frozenset(token.strip() for token in spec.split(","))


def _parse_names(spec: Optional[str]) -> List[str]:
    if not spec:
        return []
    names = [name.strip() for name in spec.split(",") if name.strip()]
    if not names:
        raise InputError("column list is empty")
    return names


def _load_profile_file(path: Path) -> DatasetProfile:
    if not path.is_file():
        raise InputError(f"baseline profile not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileError(f"{path}: not valid JSON ({exc.msg})") from None
    try:
        return profile_from_dict(data)
    except ProfileError as exc:
        raise ProfileError(f"{path}: {exc}") from None


def _apply_column_filters(
    baseline: DatasetProfile,
    current: Dataset,
    include: List[str],
    exclude: List[str],
) -> "tuple[DatasetProfile, Dataset]":
    if not include and not exclude:
        return baseline, current
    baseline_names = {col.name for col in baseline.columns}
    current_names = set(current.columns)
    for name in include:
        if name not in baseline_names and name not in current_names:
            raise InputError(f"--columns: column '{name}' not found in either snapshot")

    def keep(name: str) -> bool:
        if include and name not in include:
            return False
        return name not in exclude

    filtered_profile = dataclasses.replace(
        baseline, columns=[col for col in baseline.columns if keep(col.name)]
    )
    kept_columns = [name for name in current.columns if keep(name)]
    filtered_dataset = dataclasses.replace(
        current,
        columns=kept_columns,
        values={name: current.values[name] for name in kept_columns},
    )
    return filtered_profile, filtered_dataset


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
