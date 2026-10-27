#!/usr/bin/env python
"""Executa o pipeline de ingestão/validação/indicadores manualmente.

Uso:
    python scripts/run_pipeline.py [--trigger manual|scheduled]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import settings  # noqa: E402
from src.pipeline import run_pipeline  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline diário do Ibovespa Analytics")
    parser.add_argument("--trigger", choices=["manual", "scheduled"], default="manual")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    summary = run_pipeline(trigger=args.trigger)

    print("\n=== Resumo da execução ===")
    print(f"Status geral: {summary['status']}")
    print(f"Data de referência: {summary['reference_date']}")
    print(f"Registros lidos: {summary.get('records_read', 0)}")
    print(f"Registros gravados: {summary.get('records_written', 0)}")
    if summary.get("staleness_warning"):
        print(f"Aviso de defasagem: {summary['staleness_warning']}")
    for step in summary.get("steps", []):
        print(f"  - {step['source']}: {step['status']} (lidos={step['read']}, gravados={step['written']})"
              + (f" | erro: {step['error']}" if step.get("error") else ""))

    return 0 if summary["status"] in ("success", "partial_failure") else 1


if __name__ == "__main__":
    raise SystemExit(main())
