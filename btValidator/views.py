from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ViewSet
from django.shortcuts import get_object_or_404
from .models import TravelRequest, Document, RequestHistory, Expense  
from .data import CosmosDB
from .utils import upload_to_blob_storage
from .serializers import (
    TravelRequestSerializer, 
    DocumentSerializer, 
    RequestHistorySerializer
)
from datetime import datetime
from .utils import upload_to_blob_storage, upload_multiple_files, \
    convert_pdfs_to_base64_images, call_openai_api, extract_json_from_text, cleanup_uploaded_files
import logging
from django.conf import settings
import time, json
from rest_framework.parsers import MultiPartParser, FormParser

logger = logging.getLogger(__name__)

from rest_framework.permissions import AllowAny

class TravelRequestViewSet(ViewSet):
    #permission_classes = [IsAuthenticated]
    permission_classes = [AllowAny]  # Temporarily allow all requests
    serializer_class = TravelRequestSerializer
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        logger.info("Cosmos DB Settings:")
        logger.info(f"Endpoint: {settings.COSMOS_DB['ENDPOINT']}")
        logger.info(f"Database: {settings.COSMOS_DB['DATABASE']}")
        logger.info(f"Container: {settings.COSMOS_DB['CONTAINER']}")
        logger.info(f"Has Primary Key: {bool(settings.COSMOS_DB['PRIMARY_KEY'])}")
        self.cosmos_db = CosmosDB()

    def list(self, request):

        logger.info("=== Authenticated User Details ===")
        logger.info(f"User Name: {request.headers.get('X-MS-CLIENT-PRINCIPAL-NAME')}")
        logger.info(f"User Email: {request.headers.get('X-MS-CLIENT-PRINCIPAL-USERNAME')}")
        logger.info(f"Principal ID: {request.headers.get('X-MS-CLIENT-PRINCIPAL-ID')}")
        logger.info("=== Headers ===")
        logger.info(dict(request.headers))

        travel_requests = self.cosmos_db.list_travel_requests()
        serializer = TravelRequestSerializer(travel_requests, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        travel_request = self.cosmos_db.get_travel_request(pk)
        if not travel_request:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = TravelRequestSerializer(travel_request)
        return Response(serializer.data)

    def create(self, request):
        serializer = TravelRequestSerializer(data=request.data)
        if serializer.is_valid():
            # Add requester information
            travel_request = serializer.save(
                requester=request.user.email,
                status='PENDING'
            )
            
            history_entry = RequestHistory(
                type='created',
                title='Request Created',
                user=request.user.email,
                comments='Travel request submitted for approval'
            )
            travel_request.history.append(history_entry)
            
            created_request = self.cosmos_db.create_travel_request(travel_request)
            return Response(TravelRequestSerializer(created_request).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        travel_request = self.cosmos_db.get_travel_request(pk)
        if not travel_request:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # Create history entry
        history_entry = RequestHistory(
            type='approved',
            title='Request Approved',
            user=request.user.email,
            comments=request.data.get('comments', '')
        )
        
        # Update request
        updates = {
            'status': 'APPROVED',
            'history': travel_request.history + [history_entry],
            'updated_at': datetime.utcnow().isoformat()
        }
        
        updated_request = self.cosmos_db.update_travel_request(pk, updates)
        return Response(TravelRequestSerializer(updated_request).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        travel_request = self.cosmos_db.get_travel_request(pk)
        if not travel_request:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # Create history entry
        history_entry = RequestHistory(
            type='rejected',
            title='Request Rejected',
            user=request.user.email,
            comments=request.data.get('comments', '')
        )
        
        # Update request
        updates = {
            'status': 'REJECTED',
            'history': travel_request.history + [history_entry],
            'updated_at': datetime.utcnow().isoformat()
        }
        
        updated_request = self.cosmos_db.update_travel_request(pk, updates)
        return Response(TravelRequestSerializer(updated_request).data)

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        travel_request = self.cosmos_db.get_travel_request(pk)
        if not travel_request:
            return Response(status=status.HTTP_404_NOT_FOUND)

        assignee_email = request.data.get('assignee_email')
        comments = request.data.get('comments', '')
        
        # Create history entry
        history_entry = RequestHistory(
            type='assigned',
            title='Request Assigned',
            user=request.user.email,
            comments=f"Assigned to {assignee_email}. {comments}"
        )
        
        # Update request
        updates = {
            'history': travel_request.history + [history_entry],
            'updated_at': datetime.utcnow().isoformat()
        }
        
        updated_request = self.cosmos_db.update_travel_request(pk, updates)
        return Response(TravelRequestSerializer(updated_request).data)

    @action(detail=True, methods=['post'])
    def upload_document(self, request, pk=None):
        travel_request = self.cosmos_db.get_travel_request(pk)
        if not travel_request:
            return Response(status=status.HTTP_404_NOT_FOUND)

        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Upload to Blob Storage
            file_url = upload_to_blob_storage(file)
            
            # Create document
            document = Document(
                file_name=file.name,
                file_size=file.size,
                file_url=file_url
            )
            
            # Update request
            updates = {
                'documents': travel_request.documents + [document],
                'updated_at': datetime.utcnow().isoformat()
            }
            
            updated_request = self.cosmos_db.update_travel_request(pk, updates)
            return Response(DocumentSerializer(document).data)
            
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

    @action(detail=False, methods=['post'], url_path='generate-report')
    def generate_report(self, request):
        """
        Process uploaded PDFs and extract expense information
        """
        
        try:
            # Get files from request
            files = request.FILES.getlist('files')
            
            # Validate files
            if not files:
                return Response(
                    {'error': 'No files provided'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            if len(files) > 5:
                return Response(
                    {'error': 'Maximum 5 files allowed'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Validate each file
            for file in files:
                if file.size > settings.AZURE_STORAGE['MAX_FILE_SIZE']:
                    return Response(
                        {'error': f'File {file.name} exceeds 10MB limit'}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                if file.content_type not in settings.AZURE_STORAGE['ALLOWED_FILE_TYPES']:
                    return Response(
                        {'error': f'File {file.name} is not a PDF'}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )

            # Convert PDFs to base64 images
            try:
                base64_images = convert_pdfs_to_base64_images(files)
                logger.info(f"Successfully converted {len(base64_images)} pages to images")
            except Exception as e:
                logger.error(f"Error converting PDFs: {str(e)}")
                return Response(
                    {'error': f'Error processing PDF files: {str(e)}'}, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # Define schema for expense extraction
            schema = {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "date": {
                            "type": "string",
                            "format": "date",
                            "description": "Date of the expense (YYYY-MM-DD)"
                        },
                        "category": {
                            "type": "string",
                            "description": "Category of expense (e.g., Transportation, Accommodation, Meals)"
                        },
                        "description": {
                            "type": "string",
                            "description": "Detailed description of the expense"
                        },
                        "amount": {
                            "type": "number",
                            "description": "Amount of the expense"
                        }
                    },
                    "required": ["date", "category", "description", "amount"]
                }
            }

            # Call OpenAI API for each image
            try:
                responses = call_openai_api(base64_images, json.dumps(schema))
                logger.info(f"Received {len(responses)} responses from OpenAI")
            except Exception as e:
                logger.error(f"Error calling OpenAI API: {str(e)}")
                return Response(
                    {'error': f'Error extracting information: {str(e)}'}, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # Process responses and combine expenses
            all_expenses = []
            for response in responses:
                try:
                    expenses = extract_json_from_text(response)
                    if isinstance(expenses, list):
                        all_expenses.extend(expenses)
                except json.JSONDecodeError as e:
                    logger.warning(f"Error parsing OpenAI response: {str(e)}")
                    continue

            # Store file information for later upload
            file_info = [{
                'name': file.name,
                'size': file.size,
                'content_type': file.content_type
            } for file in files]

            # Prepare response with dummy data and extracted expenses
            extracted_data = {
                'requester': 'John Doe',
                'department': 'Engineering',
                'position': 'Software Engineer',
                'start_date': '2024-01-15',
                'end_date': '2024-01-20',
                'total_amount': sum(expense['amount'] for expense in all_expenses if 'amount' in expense),
                'expenses': all_expenses,
                'files': file_info
            }

            return Response(extracted_data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error in generate_report: {str(e)}")
            return Response(
                {'error': f'Error processing request: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
    @action(detail=True, methods=['put'], url_path='update-report')
    def update_report(self, request, pk=None):
        """
        Update a travel request with edited report data
        """
        try:
            travel_request = self.cosmos_db.get_travel_request(pk)
            if not travel_request:
                return Response(
                    {'error': 'Travel request not found'}, 
                    status=status.HTTP_404_NOT_FOUND
                )

            # Create history entry for the update
            history_entry = RequestHistory(
                type='updated',
                title='Report Updated',
                user=request.user.email,
                comments='Report details were updated'
            )

            # Update the travel request with new data
            updates = {
                'requester': request.data.get('requester', travel_request.requester),
                'department': request.data.get('department', travel_request.department),
                'position': request.data.get('position', travel_request.position),
                'start_date': request.data.get('start_date', travel_request.start_date),
                'end_date': request.data.get('end_date', travel_request.end_date),
                'total_amount': request.data.get('total_amount', travel_request.total_amount),
                'expenses': request.data.get('expenses', travel_request.expenses),
                'updated_at': datetime.utcnow().isoformat(),
                'history': travel_request.history + [history_entry]
            }
            
            # Update in Cosmos DB
            updated_request = self.cosmos_db.update_travel_request(pk, updates)
            
            return Response(TravelRequestSerializer(updated_request).data)

        except Exception as e:
            return Response(
                {'error': f'Error updating report: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'], url_path='submit-report', parser_classes=[MultiPartParser, FormParser])
    def submit_report(self, request):
        """
        Create a new travel request from the user-validated extracted data
        """
        uploaded_files = []
        try:
            # Get files from request
            files = request.FILES.getlist('files')
            print(files)
            
            # Parse the JSON data from the form
            try:
                # If data is sent as a string, parse it
                if isinstance(request.data.get('data'), str):
                    data = json.loads(request.data.get('data', '{}'))
                else:
                    data = request.data.get('data', {})
                logger.info(f"Received data for submit_report: {data}")
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing JSON data: {str(e)}")
                return Response(
                    {'error': 'Invalid JSON data provided'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            if files:
                try:
                    uploaded_files = upload_multiple_files(files)
                    logger.info(f"Successfully uploaded {len(uploaded_files)} files to blob storage")
                except Exception as e:
                    logger.error(f"Error uploading files: {str(e)}")
                    return Response(
                        {'error': f'Error uploading files: {str(e)}'}, 
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )

            # Create new travel request with explicit data mapping
            request_data = {
                'requester': str(data.get('requester', '')),
                'status': 'PENDING_REVIEW',
                'department': str(data.get('department', '')),
                'position': str(data.get('position', '')),
                'start_date': data.get('start_date'),
                'end_date': data.get('end_date'),
                'total_amount': float(data.get('total_amount', 0))
            }
            
            logger.info(f"Creating travel request with data: {request_data}")
            travel_request = TravelRequest(**request_data)

            # Handle expenses
            expenses = []
            for expense_data in data.get('expenses', []):
                expense = Expense(
                    id=expense_data.get('id'),
                    category=str(expense_data.get('category', '')),
                    description=str(expense_data.get('description', '')),
                    amount=float(expense_data.get('amount', 0)),
                    date=expense_data.get('date')
                )
                expenses.append(expense)
            travel_request.expenses = expenses

            # Handle documents from uploaded files
            if uploaded_files:
                documents = []
                for file_info in uploaded_files:
                    document = Document(
                        file_name=str(file_info['name']),
                        file_size=int(file_info['size']),
                        file_url=str(file_info['url'])
                    )
                    documents.append(document)
                travel_request.documents = documents
                logger.info(f"Added {len(documents)} documents to travel request")

            # Add initial history entry
            history_entry = RequestHistory(
                type='submitted',
                title='Report Submitted',
                user=request.user.email if request.user.is_authenticated else 'anonymous',
                comments='Travel request submitted for review'
            )
            travel_request.history = [history_entry]

            # Save to Cosmos DB
            created_request = self.cosmos_db.create_travel_request(travel_request)
            logger.info(f"Successfully created travel request with ID: {created_request['id']}")

            return Response({
                'message': 'Report submitted successfully',
                'request_id': created_request['id'],
                'uploaded_files': uploaded_files
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error in submit_report: {str(e)}")
            if 'uploaded_files' in locals() and uploaded_files:
                cleanup_uploaded_files(uploaded_files)
            return Response(
                {'error': f'Error submitting report: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )