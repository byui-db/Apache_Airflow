import sys

from airflow.dag_processing.dagbag import DagBag

DAGS_FOLDER = "/opt/airflow/dags"


def test_dags_import_cleanly():
    sys.path.insert(0, DAGS_FOLDER)  # Airflow puts dags/ on the path; DAGs import `utils` directly
    dagbag = DagBag(dag_folder=DAGS_FOLDER)
    assert not dagbag.import_errors, dagbag.import_errors
