import pandas as pd
import polars as pl

from dags.utils import save_dataframe


def test_save_dataframe_pandas_and_polars_match(tmp_path):
    data = {"a": [1, 2], "b": ["x", "y"]}
    pandas_csv = tmp_path / "pandas.csv"
    polars_csv = tmp_path / "polars.csv"

    save_dataframe(pd.DataFrame(data), str(pandas_csv))
    save_dataframe(pl.DataFrame(data), str(polars_csv))

    assert pandas_csv.read_text() == polars_csv.read_text() == "a,b\n1,x\n2,y\n"
