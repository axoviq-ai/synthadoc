# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations
import sys
from dataclasses import dataclass
from rich.console import Console
from synthadoc.config import CostConfig

# Console bound to sys.stdout so output is captured by pytest's capsys.
# highlight=False avoids Rich's internal buffering that can swallow output
# during tests.
console = Console(file=sys.stdout, highlight=False)


class CostGateError(Exception):
    pass


@dataclass
class CostEstimate:
    tokens: int
    cost_usd: float
    operation: str


class CostGuard:
    def __init__(self, config: CostConfig) -> None:
        self._cfg = config

    def check(self, estimate: CostEstimate, auto_confirm: bool = False,
              interactive: bool = True) -> None:
        if estimate.cost_usd >= self._cfg.hard_gate_usd:
            print(
                f"Cost gate: {estimate.operation} estimated "
                f"${estimate.cost_usd:.4f} (limit ${self._cfg.hard_gate_usd:.2f})",
                flush=True,
            )
            if auto_confirm:
                return
            if not interactive:
                raise CostGateError(
                    f"Estimated cost ${estimate.cost_usd:.4f} exceeds "
                    f"hard_gate_usd ${self._cfg.hard_gate_usd:.2f}. "
                    f"Raise hard_gate_usd in [cost] config or use a smaller model."
                )
            if input("Proceed? [y/N] ").strip().lower() != "y":
                raise CostGateError("Aborted by user.")
            return
        if estimate.cost_usd >= self._cfg.soft_warn_usd:
            print(
                f"Cost warning: {estimate.operation} estimated ${estimate.cost_usd:.4f}",
                flush=True,
            )
