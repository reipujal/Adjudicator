import pandas as pd


def to_excel(records: list, path: str) -> None:
    df = pd.DataFrame([vars(r) for r in records])
    df.to_excel(path, index=False)
