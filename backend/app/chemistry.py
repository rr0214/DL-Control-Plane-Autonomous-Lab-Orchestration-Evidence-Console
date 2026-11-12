"""Composition parsing and normalization. Pure functions, no I/O."""
from __future__ import annotations

import re

_TOKEN = re.compile(r"([A-Z][a-z]?)(\d+(?:\.\d+)?)")


def parse(composition: str) -> dict[str, float]:
    """'Nb50-Ti20-Cr15-Al15' -> {'Nb': 50.0, 'Ti': 20.0, 'Cr': 15.0, 'Al': 15.0}"""
    return {element: float(amount) for element, amount in _TOKEN.findall(composition)}


def elements_in(composition: str) -> set[str]:
    return set(parse(composition))


def normalize_composition(composition: str) -> str:
    """Order-independent form, so 'Ti20-Nb50-Al15-Cr15' matches 'Nb50-Ti20-Cr15-Al15'."""
    return "-".join(f"{el}{amt:g}" for el, amt in sorted(parse(composition).items()))


def normalize_processing(processing: str) -> str:
    return processing.strip().lower()
