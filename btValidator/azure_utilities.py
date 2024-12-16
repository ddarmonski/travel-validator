# btValidator/azure_utils.py

from azure.storage.blob import BlobServiceClient
from azure.cosmos import CosmosClient
from django.conf import settings
import uuid
import logging

logger = logging.getLogger(__name__)

class AzureStorageClient:
    def __init__(self):
        self.connection_string = settings.AZURE_STORAGE['CONNECTION_STRING']
        self.container_name = settings.AZURE_STORAGE['CONTAINER_NAME']
        self.client = None
        self.container_client = None
        self.initialize_client()

    def initialize_client(self):
        try:
            self.client = BlobServiceClient.from_connection_string(self.connection_string)
            self.container_client = self.client.get_container_client(self.container_name)
        except Exception as e:
            logger.error(f"Failed to initialize Azure Blob Storage: {str(e)}")
            raise

    def upload_file(self, file, content_type='application/pdf'):
        """
        Upload a file to Azure Blob Storage
        """
        try:
            # Generate unique blob name
            blob_name = f"{uuid.uuid4()}-{file.name}"
            blob_client = self.container_client.get_blob_client(blob_name)

            # Upload the file
            blob_client.upload_blob(
                file.read(),
                blob_type="BlockBlob",
                content_settings={
                    "content_type": content_type
                }
            )

            # Return the blob URL
            return blob_client.url

        except Exception as e:
            logger.error(f"Failed to upload file to blob storage: {str(e)}")
            raise

    def delete_file(self, blob_url):
        """
        Delete a file from Azure Blob Storage
        """
        try:
            # Extract blob name from URL
            blob_name = blob_url.split('/')[-1]
            blob_client = self.container_client.get_blob_client(blob_name)
            blob_client.delete_blob()
        except Exception as e:
            logger.error(f"Failed to delete blob: {str(e)}")
            raise

class CosmosDBClient:
    def __init__(self):
        self.endpoint = settings.COSMOS_DB['ENDPOINT']
        self.key = settings.COSMOS_DB['PRIMARY_KEY']
        self.database_name = settings.COSMOS_DB['DATABASE']
        self.container_name = settings.COSMOS_DB['CONTAINER']
        self.client = None
        self.database = None
        self.container = None
        self.initialize_client()

    def initialize_client(self):
        try:
            self.client = CosmosClient(self.endpoint, credential=self.key)
            self.database = self.client.get_database_client(self.database_name)
            self.container = self.database.get_container_client(self.container_name)
        except Exception as e:
            logger.error(f"Failed to initialize Cosmos DB: {str(e)}")
            raise

def verify_azure_connections():
    """
    Verify both Azure Blob Storage and Cosmos DB connections
    """
    status = {
        'blob_storage': False,
        'cosmos_db': False,
        'errors': []
    }

    # Test Blob Storage
    try:
        storage_client = AzureStorageClient()
        storage_client.container_client.get_container_properties()
        status['blob_storage'] = True
    except Exception as e:
        status['errors'].append(f"Blob Storage Error: {str(e)}")

    # Test Cosmos DB
    try:
        cosmos_client = CosmosDBClient()
        cosmos_client.container.read()
        status['cosmos_db'] = True
    except Exception as e:
        status['errors'].append(f"Cosmos DB Error: {str(e)}")

    return status