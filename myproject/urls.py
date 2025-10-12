from django.urls import path
from api.views import add_camera_data, TagReaderView

urlpatterns = [
    path('api/camera/', add_camera_data, name='add-camera'),
    path('api/tagreader/', TagReaderView.as_view(), name='tag-reader'),
]
