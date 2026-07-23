"""
create_docker_image.py

Registers the Docker image as an Azure ML Environment in the AML workspace.
Run this after building and pushing the Docker image to ACR.

Usage:
    python schedules/create_docker_image.py
    python schedules/create_docker_image.py --env prod
"""

import os
import json
import logging
import argparse
from azure.ai.ml import MLClient
from azure.ai.ml.entities import Environment
from azure.identity import DefaultAzureCredential, AzureCliCredential

# Parse arguments
parser = argparse.ArgumentParser()
parser.add_argument(
    "--env",
    type=str,
    default="dev",
    help="Deployment environment (dev, prod).",
)
args = parser.parse_args()
env_name = args.env.lower()

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Project root
project_root = os.path.dirname(os.path.abspath(__file__))
os.chdir(project_root)
logging.info(f"Project root: {project_root}")

# Load configuration based on environment
config_filename = "config.json" if env_name == "dev" else f"config_{env_name}.json"
config_path = os.path.join(project_root, "configs", config_filename)
if not os.path.exists(config_path):
    raise FileNotFoundError(
        f"Config file not found for environment '{env_name}': {config_path}"
    )
with open(config_path, "rt") as f:
    config = json.load(f)
logging.info(f"Environment: {env_name}, Config path: {config_path}")

# Extract configuration parameters
azure_config = config["azure"]
subscription_id = azure_config["subscription_id"]
resource_group = azure_config["resource_group"]
workspace_name = azure_config["workspace_name"]

pipeline_config = config["pipeline"]
environment_name = pipeline_config["environment_name"]
docker_image = pipeline_config["docker_image"]

# Connect to the Azure ML workspace
try:
    credential = AzureCliCredential()
    ml_client = MLClient(credential, subscription_id, resource_group, workspace_name)
    ml_client.models.list()
except Exception:
    credential = DefaultAzureCredential()
    ml_client = MLClient(credential, subscription_id, resource_group, workspace_name)
    ml_client.models.list()
logging.info(
    f"Connected to workspace: {workspace_name} using credential: {type(credential).__name__}"
)

# Register an AML Environment that points to the existing Docker image
env = Environment(name=environment_name, image=docker_image)
logging.info(f"Environment name: {environment_name}")

env.environment_variables = {
    "AZUREML_CONDA_ENVIRONMENT_PATH": f"/opt/conda/envs/{environment_name}"
}

# Register the environment in the workspace
ml_client.environments.create_or_update(env)
logging.info(f"Environment {env.name} created and registered.")
