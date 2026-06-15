# akv_secret_retrieval.py

from azure.identity import DefaultAzureCredential, AzureCliCredential  # type: ignore
from azure.keyvault.secrets import SecretClient  # type: ignore
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

keyvault_url =  "https://glccbdsdevkv.vault.azure.net/"
secret_name = 'chris-anderson-anthropic'

try:
    credential = DefaultAzureCredential()
    secret_client = SecretClient(vault_url=keyvault_url, credential=credential)
    akv_secret = secret_client.get_secret(secret_name)  # verifying can use credential
except Exception:
    credential = AzureCliCredential()
    secret_client = SecretClient(vault_url=keyvault_url, credential=credential)
    akv_secret = secret_client.get_secret(secret_name)  # verifying can use credential
logger.warning(f"Successfully authenticated to Key Vault and received secret using " f"credential method: {type(credential).__name__}")
