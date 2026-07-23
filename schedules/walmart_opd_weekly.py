# create_pipeline.py
#
# Walmart OPD Weekly Analysis Pipeline
# Components:
#   1. Run the agentic-data-analyst pipeline against the Alsip DC semantic model
#
# Usage:
#   python schedules/walmart_opd_weekly.py              # Submit pipeline job immediately
#   python schedules/walmart_opd_weekly.py --schedule   # Create/update scheduled job
#   python schedules/walmart_opd_weekly.py --env prod   # Use prod config
#   python schedules/walmart_opd_weekly.py --disable    # Disable existing schedule
#   python schedules/walmart_opd_weekly.py --enable     # Re-enable schedule
#   python schedules/walmart_opd_weekly.py --delete     # Delete schedule

import os
import uuid
import argparse
import json
import logging
import datetime

from azure.ai.ml import MLClient, command
from azure.ai.ml.entities import CronTrigger, JobSchedule
from azure.identity import AzureCliCredential, DefaultAzureCredential
from azure.ai.ml.constants import TimeZone

# Parse arguments
parser = argparse.ArgumentParser(
    description="Submit or schedule the Walmart OPD Weekly analysis pipeline."
)
parser.add_argument(
    "--env",
    type=str,
    default="dev",
    help="Deployment environment (dev, prod).",
)
parser.add_argument(
    "--schedule",
    action="store_true",
    default=False,
    help="Create/update a recurring schedule instead of submitting immediately.",
)
parser.add_argument(
    "--disable",
    action="store_true",
    default=False,
    help="Disable an existing schedule.",
)
parser.add_argument(
    "--enable",
    action="store_true",
    default=False,
    help="Enable a disabled schedule.",
)
parser.add_argument(
    "--delete",
    action="store_true",
    default=False,
    help="Delete an existing schedule.",
)
args = parser.parse_args()
env_name = args.env.lower()

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Project root (the agentic-data-analyst repo)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(project_root)
logger.info(f"Project root: {project_root}")

# Load configuration based on environment
config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs")
config_filename = "config.json" if env_name == "dev" else f"config_{env_name}.json"
config_path = os.path.join(config_dir, config_filename)
if not os.path.exists(config_path):
    raise FileNotFoundError(
        f"Config file not found for environment '{env_name}': {config_path}"
    )
with open(config_path, "rt") as f:
    config = json.load(f)
logger.info(f"Environment: {env_name}, Config: {config_path}")

# Extract configuration
azure_config = config["azure"]
subscription_id = azure_config["subscription_id"]
resource_group = azure_config["resource_group"]
workspace_name = azure_config["workspace_name"]

pipeline_config = config["pipeline"]
compute_target = pipeline_config["compute_target"]
environment_name = pipeline_config["environment_name"]
docker_image = pipeline_config["docker_image"]

schedule_config = config["schedule"]
schedule_name = schedule_config["name"]
schedule_display_name = schedule_config["display_name"]
schedule_description = schedule_config["description"]
cron_expression = schedule_config["cron_expression"]
time_zone = schedule_config["time_zone"]

analysis_config = config["analysis"]
domain = analysis_config["domain"]
backend = analysis_config["backend"]
source = analysis_config["source"]
question = analysis_config["question"]

notification_config = config.get("notification", {})
teams_webhook_url = notification_config.get("teams_webhook_url", "")

tags = config.get("tags", {})
tags.update({
    "domain": domain,
    "backend": backend,
    "schedule": schedule_name,
})

# ==============================================================================
# CONNECT TO AML WORKSPACE
# ==============================================================================
try:
    credential = AzureCliCredential()
    ml_client = MLClient(credential, subscription_id, resource_group, workspace_name)
    ml_client.compute.list()  # verify connection
    logger.info("Connected using AzureCliCredential")
except Exception:
    credential = DefaultAzureCredential()
    ml_client = MLClient(credential, subscription_id, resource_group, workspace_name)
    ml_client.compute.list()
    logger.info("Connected using DefaultAzureCredential")

logger.info(f"Workspace: {workspace_name}")

# ==============================================================================
# DEFINE PIPELINE JOB
# ==============================================================================

# Build the command that runs the analysis pipeline + Teams notification
# AML captures stdout/stderr in user_logs/std_log.txt automatically.
# We also copy the run artifacts to AML's outputs/ folder so they're visible in Studio.
run_command = (
    f"python -m src.main "
    f"--backend {backend} "
    f"--domain {domain} "
    f"--source {source} "
    f'--question "{question}" '
    f'&& cp -r runs/$(ls -1t runs/ | head -1)/* ./outputs/ '
)

# Chain Teams notification after successful pipeline run
if teams_webhook_url:
    notify_cmd = (
        f' && python tools/notify_teams.py '
        f'--run-dir runs/$(ls -1t runs/ | head -1) '
        f'--webhook-url "{teams_webhook_url}"'
    )
    run_command += notify_cmd

# Collect secrets from the current environment to forward to the AML job.
# The AML container has no az cli / Key Vault access, so we pull all secrets
# at submission time (using local credentials) and inject them as env vars.
import dotenv
dotenv.load_dotenv(os.path.join(project_root, ".env"))

forwarded_env_vars = {}
for key in os.environ:
    if key.startswith(("SNOWFLAKE_", "ANTHROPIC_", "PIPELINE_", "AZURE_")) or key == "TEAMS_WEBHOOK_URL":
        forwarded_env_vars[key] = os.environ[key]

# Pull secrets from Key Vault at submission time
try:
    from azure.identity import AzureCliCredential as _Cred
    from azure.keyvault.secrets import SecretClient as _SC
    _kv = _SC(vault_url="https://glccbdsdevkv.vault.azure.net/", credential=_Cred())

    # Anthropic API key (use sonnet-dev key for foundry-sonnet5 backend)
    if "ANTHROPIC_API_KEY" not in forwarded_env_vars:
        _secret = _kv.get_secret("raghu-sonnet-dev")
        forwarded_env_vars["ANTHROPIC_API_KEY"] = _secret.value
        logger.info("Loaded ANTHROPIC_API_KEY from Key Vault (raghu-sonnet-dev)")

    # Snowflake credentials (private key auth)
    if "SNOWFLAKE_ACCOUNT" not in forwarded_env_vars:
        _sf_secrets = {
            "SNOWFLAKE_ACCOUNT": "reyesholdings.east-us-2.azure",
            "SNOWFLAKE_WAREHOUSE": "CCB_DATASCIENCE_S_WH",
            "SNOWFLAKE_ROLE": "CCB_DATASCIENCE_SNOWFLAKE",
            "SNOWFLAKE_DATABASE": "CCB_DATASCIENCE_DEV",
            "SNOWFLAKE_SCHEMA": "PUBLIC",
        }
        forwarded_env_vars.update(_sf_secrets)
        try:
            import base64
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption

            forwarded_env_vars["SNOWFLAKE_USER"] = _kv.get_secret("snowflake-etl-username").value
            pem_key = _kv.get_secret("snowflake-etl-private-key-raw").value
            passphrase = _kv.get_secret("snowflake-etl-private-key-passphrase").value

            # Convert PEM + passphrase → DER bytes → base64 string
            private_key = serialization.load_pem_private_key(
                pem_key.encode(), password=passphrase.encode()
            )
            der_bytes = private_key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())
            forwarded_env_vars["SNOWFLAKE_PRIVATE_KEY"] = base64.b64encode(der_bytes).decode()
            logger.info("Loaded Snowflake credentials from Key Vault (private key → DER → base64)")
        except Exception as e:
            logger.warning(f"Could not load Snowflake creds from KV: {e}")

except Exception as e:
    logger.warning(f"Could not load secrets from KV: {e}. Job may fail if creds not in env.")

pipeline_job = command(
    name=f"walmart_opd_weekly_{uuid.uuid4().hex[:8]}",
    display_name=schedule_display_name,
    description=schedule_description,
    command=run_command,
    compute=compute_target,
    environment=f"azureml:{environment_name}:2",
    code=".",  # ships the entire repo as the job's working directory
    environment_variables=forwarded_env_vars,
    is_deterministic=False,
    tags=tags,
)

# ==============================================================================
# SUBMIT OR SCHEDULE
# ==============================================================================

if args.disable:
    logger.info(f"Disabling schedule: {schedule_name}")
    schedule = ml_client.schedules.get(schedule_name)
    schedule.is_enabled = False
    result = ml_client.schedules.begin_create_or_update(schedule).result()
    logger.info(f"Schedule disabled: {result.name}")

elif args.enable:
    logger.info(f"Enabling schedule: {schedule_name}")
    schedule = ml_client.schedules.get(schedule_name)
    schedule.is_enabled = True
    result = ml_client.schedules.begin_create_or_update(schedule).result()
    logger.info(f"Schedule enabled: {result.name}")

elif args.delete:
    logger.info(f"Deleting schedule: {schedule_name}")
    ml_client.schedules.begin_delete(schedule_name).result()
    logger.info(f"Schedule deleted: {schedule_name}")

elif args.schedule:
    # SCHEDULED: Create/update a recurring schedule
    logger.info(f"Creating/updating schedule: {schedule_name}")

    cron_trigger = CronTrigger(
        expression=cron_expression,
        time_zone=TimeZone.CENTRAL_STANDARD_TIME,
    )

    schedule = JobSchedule(
        name=schedule_name,
        display_name=schedule_display_name,
        description=schedule_description,
        trigger=cron_trigger,
        create_job=pipeline_job,
    )

    try:
        result = ml_client.schedules.begin_create_or_update(schedule).result()
        logger.info(f"Schedule created/updated: {result.name}")
        logger.info(f"  Cron: {cron_expression} ({time_zone})")
        logger.info(f"  Enabled: {result.is_enabled}")
    except Exception as e:
        raise Exception(f"Error creating schedule: {e}")

else:
    # IMMEDIATE: Submit and run now
    unique_name = (
        f"walmart_opd_weekly_{uuid.uuid4().hex[:8]}_"
        f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    )
    pipeline_job.name = unique_name
    logger.info(f"Submitting job: {unique_name}")

    result = ml_client.jobs.create_or_update(pipeline_job)
    logger.info(f"Job submitted: {result.name}")
    logger.info(f"  Studio URL: {result.studio_url}")

    try:
        ml_client.jobs.stream(result.name)
    except Exception as e:
        logger.error(f"Error streaming job logs: {e}")
        raise
