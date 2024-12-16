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

import logging
from django.conf import settings
import time 
logger = logging.getLogger(__name__)

from rest_framework.permissions import AllowAny

class TravelRequestViewSet(ViewSet):
    # permission_classes = [IsAuthenticated]
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
        Handle file uploads and return extracted data without saving to database
        """
        try:
            files = list(request.FILES.values())
            
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

            # Validate files
            for file in files:
                if file.size > 10 * 1024 * 1024:  # 10MB limit
                    return Response(
                        {'error': f'File {file.name} exceeds 10MB limit'}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                if not file.name.lower().endswith('.pdf'):
                    return Response(
                        {'error': f'File {file.name} is not a PDF'}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )

            # Dummy extracted data (in real implementation, this would come from PDF extraction)
            extracted_data = {
                'requester': 'John Doe',
                'department': 'Engineering',
                'position': 'Software Engineer',
                'start_date': '2024-01-15',
                'end_date': '2024-01-20',
                'total_amount': 1250.50,
                'expenses': [
                    {
                        'id': '1',
                        'date': '2024-01-15',
                        'category': 'Transportation',
                        'description': 'Flight to New York',
                        'amount': 450.00
                    },
                    {
                        'id': '2',
                        'date': '2024-01-16',
                        'category': 'Accommodation',
                        'description': 'Hotel Stay',
                        'amount': 800.50
                    }
                ],
                'uploaded_files': [
                    {
                        'name': file.name,
                        'size': file.size
                    } for file in files
                ]
            }

            return Response(extracted_data, status=status.HTTP_200_OK)

        except Exception as e:
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

    @action(detail=False, methods=['post'], url_path='submit-report')
    def submit_report(self, request):
        """
        Create a new travel request from the user-validated extracted data
        """
          
        try:
            time.sleep(2)
            data = request.data
            print(f"Received data for submit_report: {data}")  # Add this logging
            
            # Create new travel request with explicit data mapping
            request_data = {
                'requester': str(data.get('requester')),  # Convert to string explicitly
                'status': 'PENDING_REVIEW',
                'department': str(data.get('department')),
                'position': str(data.get('position')),
                'start_date': data.get('start_date'),
                'end_date': data.get('end_date'),
                'total_amount': float(data.get('total_amount', 0))
            }
            
            print(f"Mapped request data: {request_data}")  # Add this logging
            
            travel_request = TravelRequest(**request_data)

            # Handle expenses
            expenses = []
            for expense_data in data.get('expenses', []):
                expense = Expense(
                    id=expense_data.get('id'),  # Include id if present
                    category=str(expense_data.get('category')),
                    description=str(expense_data.get('description')),
                    amount=float(expense_data.get('amount', 0)),
                    date=expense_data.get('date')
                )
                expenses.append(expense)
            travel_request.expenses = expenses

            # Handle uploaded files
            if isinstance(data.get('uploaded_files'), list):  # Check if it's a list
                documents = []
                for file_info in data.get('uploaded_files', []):
                    document = Document(
                        file_name=str(file_info.get('name')),
                        file_size=int(file_info.get('size', 0)),
                        file_url="placeholder_url"
                    )
                    documents.append(document)
                travel_request.documents = documents

            # Add initial history entry
            history_entry = RequestHistory(
                type='submitted',
                title='Report Submitted',
                user=request.user.email if request.user.is_authenticated else 'anonymous',
                comments='Travel request submitted for review'
            )
            travel_request.history = [history_entry]

            # Log the complete travel request before saving
            print(f"Travel request before save: {travel_request.to_dict()}")

            # Save to Cosmos DB
            created_request = self.cosmos_db.create_travel_request(travel_request)
            print(f"Created request response: {created_request}")  # Add this logging

            return Response({
                'message': 'Report submitted successfully',
                'request_id': created_request['id']
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error in submit_report: {str(e)}")
            return Response(
                {'error': f'Error submitting report: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )