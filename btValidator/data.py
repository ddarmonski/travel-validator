from azure.cosmos import CosmosClient, PartitionKey
from django.conf import settings
from .models import TravelRequest
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class CosmosDB:
    def __init__(self):
        
        endpoint = settings.COSMOS_DB['ENDPOINT']
        key = settings.COSMOS_DB['PRIMARY_KEY']
        database = settings.COSMOS_DB['DATABASE']
        container = settings.COSMOS_DB['CONTAINER']

        logger.info(f"Endpoint type: {type(endpoint)}")
        logger.info(f"Key type: {type(key)}")
        logger.info(f"Database: {database}")
        logger.info(f"Container: {container}")

        try:
            # Initialize with url and credential parameters explicitly
            self.client = CosmosClient(
                url=settings.COSMOS_DB['ENDPOINT'],
                credential=settings.COSMOS_DB['PRIMARY_KEY']
            )
            
            # Get database reference
            self.database = self.client.get_database_client(settings.COSMOS_DB['DATABASE'])
            
            # Get container reference
            self.container = self.database.get_container_client(settings.COSMOS_DB['CONTAINER'])
            
        except Exception as e:
            logger.error(f"Failed to initialize Cosmos DB: {str(e)}")
            raise

    def create_travel_request(self, travel_request):
        try:
            return self.container.create_item(body=travel_request.to_dict())
        except Exception as e:
            logger.error(f"Failed to create travel request: {str(e)}")
            raise

    def get_travel_request(self, request_id):
        try:
            query = f"SELECT * FROM c WHERE c.id = '{request_id}' AND c.type = 'travel_request'"
            items = list(self.container.query_items(
                query=query, 
                enable_cross_partition_query=True
            ))
            return TravelRequest.from_dict(items[0]) if items else None
        except Exception as e:
            logger.error(f"Failed to get travel request {request_id}: {str(e)}")
            return None

    def update_travel_request(self, request_id, updates):
        try:
            request = self.get_travel_request(request_id)
            if request:
                request_dict = request.to_dict()
                request_dict.update(updates)
                request_dict['updated_at'] = datetime.utcnow().isoformat()
                return self.container.upsert_item(body=request_dict)
            return None
        except Exception as e:
            logger.error(f"Failed to update travel request {request_id}: {str(e)}")
            raise

    def list_travel_requests(self, requester=None, status=None):
        try:
            query = "SELECT * FROM c WHERE c.type = 'travel_request'"
            if requester:
                query += f" AND c.requester = '{requester}'"
            if status:
                query += f" AND c.status = '{status}'"
            items = self.container.query_items(
                query=query, 
                enable_cross_partition_query=True
            )
            return [TravelRequest.from_dict(item) for item in items]
        except Exception as e:
            logger.error(f"Failed to list travel requests: {str(e)}")
            raise