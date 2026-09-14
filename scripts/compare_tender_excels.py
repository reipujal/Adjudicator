from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

DEFAULT_COLUMNS = [
    "Fecha inicio contrato",
    "Fecha fin contrato",
    "Fecha de vencimiento",
    "Prorrogable hasta",
    "Duración del contrato",
    "Número máximo de prórrogas",
    "Duración prórroga",
    "Solvencia",
    "Tecnología",
]

KEY_COLUMNS = ["Número de expediente", "Numero de expediente", "Título", "Titulo"]


def clean(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def safe_print(value: str) -> None:
    print(value.encode("cp1252", errors="backslashreplace").decode("cp1252"))


def key_column(df: pd.DataFrame) -> str:
    for candidate in KEY_COLUMNS:
        if candidate in df.columns:
            return candidate
    raise SystemExit(f"No encuentro columna clave. Candidatas: {', '.join(KEY_COLUMNS)}")


def row_key(row: pd.Series, key: str) -> str:
    value = clean(row.get(key))
    if value:
        return value
    for fallback in ["Título", "Titulo"]:
        if fallback in row:
            value = clean(row.get(fallback))
            if value:
                return value
    return ""


def read_by_key(path: Path) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    df = pd.read_excel(path)
    key = key_column(df)
    rows = {row_key(row, key): row for _, row in df.iterrows() if row_key(row, key)}
    return df, rows


def null_counts(df: pd.DataFrame, columns: list[str]) -> dict[str, int]:
    return {
        column: sum(1 for value in df[column] if clean(value) == "")
        for column in columns
        if column in df.columns
    }


def compare(left: Path, right: Path, columns: list[str]) -> int:
    left_df, left_rows = read_by_key(left)
    right_df, right_rows = read_by_key(right)
    common = sorted(set(left_rows) & set(right_rows))
    left_only = sorted(set(left_rows) - set(right_rows))
    right_only = sorted(set(right_rows) - set(left_rows))

    diffs: list[tuple[str, str, str, str]] = []
    for key in common:
        for column in columns:
            if column not in left_df.columns or column not in right_df.columns:
                continue
            old = clean(left_rows[key].get(column))
            new = clean(right_rows[key].get(column))
            if old != new:
                diffs.append((key, column, old, new))

    safe_print(f"LEFT={left}")
    safe_print(f"RIGHT={right}")
    safe_print(f"rows_left={len(left_df)} rows_right={len(right_df)} common={len(common)}")
    safe_print(f"left_only={len(left_only)} right_only={len(right_only)} diffs={len(diffs)}")
    safe_print(f"left_nulls={null_counts(left_df, columns)}")
    safe_print(f"right_nulls={null_counts(right_df, columns)}")
    if left_only:
        print("LEFT_ONLY:")
        for key in left_only[:20]:
            safe_print(f"- {key}")
    if right_only:
        print("RIGHT_ONLY:")
        for key in right_only[:20]:
            safe_print(f"- {key}")
    if diffs:
        print("DIFFS:")
        for key, column, old, new in diffs[:120]:
            safe_print(f"- {key} | {column}: {old!r} -> {new!r}")
        if len(diffs) > 120:
            print(f"... {len(diffs) - 120} more")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two TendersTool Excel exports.")
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--columns", nargs="*", default=DEFAULT_COLUMNS)
    args = parser.parse_args()
    return compare(args.left, args.right, args.columns)


if __name__ == "__main__":
    raise SystemExit(main())
