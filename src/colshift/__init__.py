"""colshift: per-column distribution drift between two dataset snapshots.

Public API surface — everything else is an implementation detail:

>>> from colshift import load_table, profile_dataset, compare, render_markdown
>>> baseline = profile_dataset(load_table("baseline.csv"))  # doctest: +SKIP
>>> report = compare(baseline, load_table("current.csv"))  # doctest: +SKIP
>>> print(render_markdown(report))  # doctest: +SKIP
"""

__version__ = "0.1.0"

from .drift import ColumnDrift, DriftReport, Thresholds, compare  # noqa: E402
from .errors import ColshiftError, InputError, ProfileError  # noqa: E402
from .inference import DEFAULT_NULL_TOKENS  # noqa: E402
from .loaders import Dataset, load_table  # noqa: E402
from .profiles import (  # noqa: E402
    ColumnProfile,
    DatasetProfile,
    profile_dataset,
    profile_from_dict,
    profile_to_dict,
)
from .report import render_json, render_markdown, report_to_dict  # noqa: E402

__all__ = [
    "__version__",
    "ColshiftError",
    "InputError",
    "ProfileError",
    "Dataset",
    "load_table",
    "DEFAULT_NULL_TOKENS",
    "ColumnProfile",
    "DatasetProfile",
    "profile_dataset",
    "profile_to_dict",
    "profile_from_dict",
    "Thresholds",
    "ColumnDrift",
    "DriftReport",
    "compare",
    "render_markdown",
    "render_json",
    "report_to_dict",
]
