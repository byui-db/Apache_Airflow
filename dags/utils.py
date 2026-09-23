import pandas as pd
import re
import snowflake.connector
from dotenv import load_dotenv
import os
import pymongo
import sshtunnel
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import base64
import logging
from sshtunnel import SSHTunnelForwarder
from pymongo import MongoClient
import stat
import paramiko

# -------------------------------------------------------------------
# Utility Functions
# -------------------------------------------------------------------
load_dotenv()

# -------------------------------------------------------------------
# S&P 500 Tickers
# -------------------------------------------------------------------
def get_sp500_tickers() -> list[str]:
    """
    Return the current S&P 500 ticker symbols from Wikipedia.

    The symbols are stripped of surrounding whitespace, de-duplicated,
    sorted alphabetically, and normalized for common market-data APIs by
    replacing periods with hyphens (for example, ``BRK.B`` becomes
    ``BRK-B``).

    Returns:
        A sorted list of ticker symbols as strings.

    Raises:
        Any exception raised by ``pandas.read_html`` if Wikipedia cannot be
        reached or its table format changes.
    """
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    # Add a User-Agent so Wikipedia doesn't block the request
    dfs = pd.read_html(
        url,
        match="Symbol",
        storage_options={"User-Agent": "Mozilla/5.0"}
    )
    df = dfs[0]

    tickers = (
        df["Symbol"]
        .astype(str)
        .str.strip()
        .dropna()
        .drop_duplicates()
        .apply(lambda t: re.sub(r"\.", "-", t))  # Replace dots with dashes
        .sort_values()  # Sort alphabetically
        .tolist()
    )
    return tickers

# -------------------------------------------------------------------
# Snowflake_keypair
# -------------------------------------------------------------------
def get_snowflake_connection(schema: str = None):
    """
    Open a Snowflake connection using key-pair authentication only.

    Connection settings are read from environment variables. The private key
    must be supplied either as a file path or as base64-encoded PEM data. A
    passphrase is optional. ``schema`` overrides ``SNOWFLAKE_SCHEMA`` when it
    is provided.

    Required environment variables:
        ``SNOWFLAKE_USER``, ``SNOWFLAKE_ACCOUNT``, and either
        ``SNOWFLAKE_PRIVATE_KEY_PATH`` or ``SNOWFLAKE_PRIVATE_KEY_B64``.

    Optional environment variables:
        ``SNOWFLAKE_ROLE``, ``SNOWFLAKE_WAREHOUSE``,
        ``SNOWFLAKE_DATABASE``, ``SNOWFLAKE_SCHEMA``, and
        ``SNOWFLAKE_PRIVATE_KEY_PASSPHRASE``.

    Args:
        schema: Snowflake schema to use instead of the configured default.

    Returns:
        An open Snowflake connection.

    Raises:
        ValueError: If neither private-key environment variable is set.
        Any exception raised while reading, decoding, or loading the key, or
        while connecting to Snowflake.
    """
    common = dict(
        user=os.getenv("SNOWFLAKE_USER"),
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        role=os.getenv("SNOWFLAKE_ROLE"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "STUDENT_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE", "PROJECT_DB"),
        schema=schema or os.getenv("SNOWFLAKE_SCHEMA", "RAW"),
    )

    key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
    key_b64  = os.getenv("SNOWFLAKE_PRIVATE_KEY_B64")
    key_pass = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")

    if not key_path and not key_b64:
        raise ValueError(
            "❌ Must set SNOWFLAKE_PRIVATE_KEY_PATH or SNOWFLAKE_PRIVATE_KEY_B64 in environment"
        )

    if key_path:
        with open(key_path, "rb") as f:
            key_pem = f.read()
    else:
        key_pem = base64.b64decode(key_b64)

    private_key = serialization.load_pem_private_key(
        key_pem,
        password=(key_pass.encode() if key_pass else None),
        backend=default_backend(),
    ).private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    return snowflake.connector.connect(private_key=private_key, **common)

# -------------------------------------------------------------------
# MongoDB
# -------------------------------------------------------------------
def get_mongo_client(local_port=None):
    """
    Create a MongoDB client from environment-based connection settings.

    Pass an SSH tunnel's local port to connect through that tunnel. When no
    local port is provided, the client connects directly to ``MONGO_HOST``.
    The password is URL-encoded before it is placed in the connection URI.

    Args:
        local_port: Local port exposed by an SSH tunnel. If omitted, use
            ``MONGO_HOST`` and ``MONGO_PORT`` instead.

    Returns:
        A ``pymongo.MongoClient`` instance. Creating the client does not
        necessarily verify the connection until MongoDB is first contacted.
    """
    from urllib.parse import quote_plus
    host = "127.0.0.1" if local_port else os.getenv("MONGO_HOST")
    port = local_port or int(os.getenv("MONGO_PORT", 27017))
    user = os.getenv("MONGO_USER")
    password = quote_plus(os.getenv("MONGO_PASSWORD"))  # URL-encode the password
    auth_db = os.getenv("MONGO_DB", "admin")

    uri = f"mongodb://{user}:{password}@{host}:{port}/{auth_db}"
    return pymongo.MongoClient(uri)

def get_mongo_collection(client):
    """
    Return the configured MongoDB collection.

    The database and collection names come from ``MONGO_DB`` and
    ``MONGO_COLLECTION``. The client must already be connected or configured
    to connect to the intended MongoDB deployment.

    Args:
        client: A ``pymongo.MongoClient`` instance.

    Returns:
        The MongoDB collection selected by the environment variables.
    """
    db_name = os.getenv("MONGO_DB")
    collection_name = os.getenv("MONGO_COLLECTION")
    return client[db_name][collection_name]


# ---------------------------------------------------------
# SSH Tunnel to MongoDB
# ---------------------------------------------------------
def create_ssh_tunnel():
    """Start an SSH tunnel that forwards local MongoDB traffic.

    SSH credentials and the remote MongoDB host and port are read from
    ``SSH_HOST``, ``SSH_PORT``, ``SSH_USER``, ``SSH_PASSWORD``, ``MONGO_HOST``,
    and ``MONGO_PORT``. The tunnel listens on ``127.0.0.1:27017`` and forwards
    traffic to the configured remote MongoDB endpoint.

    Returns:
        A started ``SSHTunnelForwarder``. Callers are responsible for stopping
        it when the connection is no longer needed.

    Raises:
        Any exception raised while creating or starting the tunnel.
    """
    SSH_HOST = os.getenv("SSH_HOST")
    SSH_PORT = int(os.getenv("SSH_PORT"))
    SSH_USER = os.getenv("SSH_USER")
    SSH_PASSWORD = os.getenv("SSH_PASSWORD")
    MONGO_HOST = os.getenv("MONGO_HOST")
    MONGO_PORT = int(os.getenv("MONGO_PORT"))

    logging.info("Starting SSH tunnel to MongoDB...")
    tunnel = SSHTunnelForwarder(
        (SSH_HOST, SSH_PORT),
        ssh_username=SSH_USER,
        ssh_password=SSH_PASSWORD,
        remote_bind_address=(MONGO_HOST, MONGO_PORT),
        local_bind_address=("127.0.0.1", 27017)
    )
    tunnel.start()
    logging.info(f"SSH tunnel established on local port {tunnel.local_bind_port}")
    return tunnel

# ---------------------------------------------------------
# Weather Record Builder
# ---------------------------------------------------------

def build_weather_record(weather_dict, target_date, city):
    """Convert one day's API weather response into a compact record.

    The function reads the first value from each daily metric and returns
    ``None`` when a metric or the ``daily`` section is missing. It does not
    validate units or transform the date and city values.

    Args:
        weather_dict: Weather API response containing an optional ``daily``
            mapping.
        target_date: Date to store in the resulting record.
        city: City name to store in the resulting record.

    Returns:
        A dictionary with ``date``, ``city``, ``max_temp``, ``min_temp``,
        ``precip``, and ``max_wind`` keys.
    """
    daily_data = weather_dict.get("daily", {})
    return {
        "date": target_date,
        "city": city,
        "max_temp": daily_data.get("temperature_2m_max", [None])[0],
        "min_temp": daily_data.get("temperature_2m_min", [None])[0],
        "precip": daily_data.get("precipitation_sum", [None])[0],
        "max_wind": daily_data.get("windspeed_10m_max", [None])[0],
    }

# ---------------------------------------------------------
# Snowflake MERGE SQL Builder
# ---------------------------------------------------------

def build_merge_sql(rec, table):
    """Build a Snowflake ``MERGE`` statement for one weather record.

    The statement updates an existing row identified by ``DATE`` and
    ``CITY`` or inserts a new row when no match exists. Numeric missing values
    are rendered as SQL ``NULL``. The table name and record values are
    interpolated directly into the returned string, so callers should pass
    trusted, validated values before executing it.

    Args:
        rec: Mapping containing ``date``, ``city``, ``max_temp``, ``min_temp``,
            ``max_wind``, and ``precip`` values.
        table: Destination Snowflake table name.

    Returns:
        The SQL text for the merge operation.
    """
    return f"""
        MERGE INTO {table} t
        USING (SELECT
            '{rec["date"]}' AS DATE,
            '{rec["city"]}' AS CITY,
            {rec["max_temp"] if rec["max_temp"] is not None else 'NULL'} AS MAX_TEMP,
            {rec["min_temp"] if rec["min_temp"] is not None else 'NULL'} AS MIN_TEMP,
            {rec["max_wind"] if rec["max_wind"] is not None else 'NULL'} AS MAX_WIND,
            {rec["precip"] if rec["precip"] is not None else 'NULL'} AS PRECIP
        ) s
        ON t.DATE = s.DATE AND t.CITY = s.CITY
        WHEN MATCHED THEN UPDATE SET
            MAX_TEMP = s.MAX_TEMP,
            MIN_TEMP = s.MIN_TEMP,
            MAX_WIND = s.MAX_WIND,
            PRECIP   = s.PRECIP
        WHEN NOT MATCHED THEN INSERT
            (DATE, CITY, MAX_TEMP, MIN_TEMP, MAX_WIND, PRECIP)
        VALUES
            (s.DATE, s.CITY, s.MAX_TEMP, s.MIN_TEMP, s.MAX_WIND, s.PRECIP);
    """

# ---------------------------------------------------------------
# SFTP Helper Utilities for Airflow DAGs
# ---------------------------------------------------------------

def create_sftp_connection():
    """
    Open an SFTP connection using username/password authentication.

    Connection settings are read from ``SFTP_HOST``, ``SFTP_PORT``,
    ``SFTP_USER``, and ``SFTP_PASSWORD``. The returned client is live and
    ready for file operations; callers should close it when finished.

    Returns:
        A live ``paramiko.SFTPClient``.

    Raises:
        Any exception raised while creating the transport or authenticating.
    """
    host = os.getenv("SFTP_HOST")
    port = int(os.getenv("SFTP_PORT", 22))
    username = os.getenv("SFTP_USER")
    password = os.getenv("SFTP_PASSWORD")

    try:
        transport = paramiko.Transport((host, port))
        transport.connect(username=username, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        logging.info(f"✅ Connected to SFTP: {host}")
        return sftp
    except Exception as e:
        logging.error(f"❌ Failed to connect to SFTP: {e}")
        raise

def is_directory(sftp, path):
    """Return whether an SFTP path points to a directory.

    Args:
        sftp: An active SFTP client with a ``stat`` method.
        path: Remote path to inspect.

    Returns:
        ``True`` when the path is a directory, otherwise ``False``. An
        ``IOError`` from a missing or inaccessible path is treated as
        ``False``.
    """
    try:
        return stat.S_ISDIR(sftp.stat(path).st_mode)
    except IOError:
        return False

def list_folders(sftp):
    """List directory names in the SFTP client's current directory.

    Args:
        sftp: An active SFTP client. Its current working directory determines
            which entries are inspected.

    Returns:
        A list of entries that are directories. If listing fails, log the
        error and return an empty list.
    """
    try:
        folders = [f for f in sftp.listdir() if is_directory(sftp, f)]
        logging.info(f"📂 Found {len(folders)} folders on SFTP.")
        return folders
    except Exception as e:
        logging.error(f"Error listing folders: {e}")
        return []

def list_files(sftp, folder):
    """Change into an SFTP folder and list its non-directory entries.

    Args:
        sftp: An active SFTP client.
        folder: Remote folder path. The client's working directory is changed
            to this folder before listing.

    Returns:
        A list of file names in ``folder``. If changing directories or
        listing fails, log the error and return an empty list.
    """
    try:
        sftp.chdir(folder)
        files = [f for f in sftp.listdir() if not is_directory(sftp, f)]
        logging.info(f"🧾 Found {len(files)} files in {folder}")
        return files
    except Exception as e:
        logging.error(f"Error listing files in {folder}: {e}")
        return []

def read_file_from_sftp(sftp, folder, filename):
    """Read a UTF-8 text file from an SFTP folder.

    Args:
        sftp: An active SFTP client with an ``open`` method.
        folder: Remote folder containing the file.
        filename: Name of the remote file to read.

    Returns:
        The complete file contents decoded as a UTF-8 string.

    Raises:
        Any exception raised while opening, reading, or decoding the file.
    """
    try:
        remote_path = os.path.join(folder, filename)
        with sftp.open(remote_path, "r") as f:
            content = f.read().decode("utf-8")
        return content
    except Exception as e:
        logging.error(f"Error reading {filename}: {e}")
        raise


def save_dataframe(df, filepath):
    """Write a pandas DataFrame to a CSV file without the index column.

    Args:
        df: DataFrame to write.
        filepath: Local or mounted filesystem path for the output CSV.

    Returns:
        ``None``. The function logs the destination after the write succeeds.

    Raises:
        Any exception raised by pandas or the filesystem when writing the
        file.
    """
    df.to_csv(filepath, index=False)
    logging.info(f"💾 Saved DataFrame to {filepath}")
