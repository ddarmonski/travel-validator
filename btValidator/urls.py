from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TravelRequestViewSet

# Create a router and register the viewset
router = DefaultRouter()
router.register(r'travel-requests', TravelRequestViewSet, basename='travel-request')

# Define URL patterns
urlpatterns = [
    path('', include(router.urls)),
]
