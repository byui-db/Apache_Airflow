# Student Airflow Template Setup

This is a ready-to-run Apache Airflow + Docker environment designed for classroom use. Students can use this to run Airflow DAGs that connect to datasources and process data pipelines.

## Walkthrough Video
[Watch: Starter DAG Walkthrough](https://video.byui.edu/media/t/1_zx5alvpi)


For README clarity, Option 2 is cleaner. Option 1 works but embeds a large iframe inline.


## Before You Start
1. Click `Use this template` and save as your own repo
2. Clone your repo, I prefer the open in GitHub Desktop method
3. Open the cloned repo in VS Code

## Docker Setup
1. Make sure you have Docker installed on your machine. You can download it from the official Docker website. Here is the link: https://docs.docker.com/get-docker/

## Setup your .env file
[Watch: Student .env Walkthrough](https://video.byui.edu/media/t/1_44saehlm)
1. Edit the `editme.env` by renaming it to just `.env`


## Local environment setup for local testing and key generation
Note: this `pip install` includes all the other libraries needed for the scripts in the Test folder to run locally outside of Docker. It also lets you run a key generation setup script for Airflow.

1. Open a new terminal in VS Code -> Terminal -> New Terminal
2. Run this code in the terminal
```bash
pip install cryptography paramiko==3.5.1 python-dotenv sshtunnel==0.4.0
```

3. Run the `airflow-core-fernet-key.py` script to generate a fernet key. This key is used to encrypt sensitive data in Airflow, such as passwords and connection strings.
```bash
python airflow-core-fernet-key.py
```

4. Copy the generated fernet key and paste it into the `.env` file in the `FERNET_KEY` variable.

## WINDOWS Generate a Public Key for Snowflake
1. Generate SSH Keys for Snowflake Connection. Run the following commands in a `git-bash shell`. (Windows users do not run in powershell, use a git-bash shell only)

```bash
mkdir -p ~/.ssh
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out ~/.ssh/dbt_key.p8 -nocrypt
openssl rsa -in ~/.ssh/dbt_key.p8 -pubout -out ~/.ssh/dbt_key.pub
cat ~/.ssh/dbt_key.pub | clip
```

2. Update `docker-compose.yaml` line 85. Look for the `# Windows Version` example comment in line 86. It is the same path as Mac but with `C:` added in front. Update the `username` to match your Windows username and add the `C:` as in the example.

3. Your public key is now copied to your clipboard — paste it when prompted by your Snowflake admin (your teacher) to set up key pair authentication.

## MAC Generate a Public Key for Snowflake

1. Generate SSH Keys for Snowflake Connection. Run the following commands in a `terminal shell`.

```bash
mkdir -p ~/.ssh
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out ~/.ssh/dbt_key.p8 -nocrypt
openssl rsa -in ~/.ssh/dbt_key.p8 -pubout -out ~/.ssh/dbt_key.pub
cat ~/.ssh/dbt_key.pub | pbcopy
```

2. Update `docker-compose.yaml` line 85. Look for the `# Mac Version` comment and update `username` in the path to match your Mac username.

3. Your public key is now copied to your clipboard — paste it when prompted by your Snowflake admin (your teacher) to set up key pair authentication.

Resource: [Snowflake Documentation on Key Pair Auth](https://docs.snowflake.com/en/user-guide/key-pair-auth)

# ✅ Getting Airflow Started

## How to Build and Spin Up the Docker Container

1. Make sure the docker app is open on your machine
2. Open a new terminal in VS Code -> Terminal -> New Terminal
3. Run this code in the terminal
```bash
docker compose up --build -d
```
Note: you only run the `--build` flag the first time or if you change something in the Dockerfile or requirements.txt. After that you can just run `docker compose up -d`

4. Open [http://localhost:8080](http://localhost:8080)

Login with:
- **Username:** `airflow`
- **Password:** `airflow`

## How to shut down docker
1. Run this in the terminal in VS Code
```bash
docker compose down
```

## Docker container troubleshooting
### Stop everything and remove containers + volumes for this project
1. This will stop all running containers, remove the containers, and delete any associated volumes for this project.
```bash
docker compose down --volumes --remove-orphans
```