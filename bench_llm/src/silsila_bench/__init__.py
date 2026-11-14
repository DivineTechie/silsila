"""Silsila-Bench: pre-registered evaluation of language models on genetic risk in cousin-marriage families.

See bench_llm/README.md and bench_llm/PREREGISTRATION.md.
"""


def main() -> None:
    from .run import main as run_main

    raise SystemExit(run_main())
