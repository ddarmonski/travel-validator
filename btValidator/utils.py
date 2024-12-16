from azure.storage.blob import BlobServiceClient
from django.conf import settings
import uuid

def upload_to_blob_storage(file, filename=None):
    try:
        # Create blob service client
        blob_service_client = BlobServiceClient.from_connection_string(
            settings.AZURE_STORAGE_CONNECTION_STRING
        )
        container_client = blob_service_client.get_container_client(settings.AZURE_STORAGE_CONTAINER)
        
        # Generate unique filename if not provided
        if not filename:
            ext = file.name.split('.')[-1]
            filename = f"{uuid.uuid4()}.{ext}"
            
        # Upload file
        blob_client = container_client.get_blob_client(filename)
        blob_client.upload_blob(file)
        
        # Return the URL of the uploaded file
        return blob_client.url
        
    except Exception as e:
        print(f"Error uploading to blob storage: {str(e)}")
        raise