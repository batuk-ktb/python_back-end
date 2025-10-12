from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import TagReader, CameraData
from .serializers import TagReaderSerializer
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json

# CameraData POST
@csrf_exempt
def add_camera_data(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            camera = CameraData.objects.create(
                container = data.get("container"),
                date = data.get("date"),
                ocrtime = data.get("ocrtime"),
                digitheight = data.get("digitheight"),
                left = data.get("left"),
                top = data.get("top"),
                right = data.get("right"),
                bottom = data.get("bottom"),
                confidencecode = data.get("confidencecode"),
                controldigit = data.get("controldigit"),
                numdigits = data.get("numdigits"),
                ownercity = data.get("ownercity"),
                ownercode = data.get("ownercode"),
                ownercompany = data.get("ownercompany"),
                readconfidence = data.get("readconfidence"),
                serialcode = data.get("serialcode"),
                sizetypecode = data.get("sizetypecode", "")
            )
            return JsonResponse({"status": "ok", "id":str(camera.id)})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})
    return JsonResponse({"status": "error", "message": "POST method required"})

# TagReader API
class TagReaderView(APIView):
    def get(self, request):
        data = TagReader.objects.all().order_by('-date')
        serializer = TagReaderSerializer(data, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = TagReaderSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
