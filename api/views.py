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
            print('data here ---',request.body)
            data = json.loads(request.body)
            camera = CameraData.objects.create(
                container=data.get("container"),
                date=data.get("date"),
                ocrtime=data.get("ocrtime"),
                digitheight=data.get("digitheight"),
                left=data.get("left"),
                top=data.get("top"),
                right=data.get("right"),
                bottom=data.get("bottom"),
                confidencecode=data.get("confidencecode"),
                controldigit=data.get("controldigit"),
                numdigits=data.get("numdigits"),
                ownercity=data.get("ownercity"),
                ownercode=data.get("ownercode"),
                ownercompany=data.get("ownercompany"),
                readconfidence=data.get("readconfidence"),
                serialcode=data.get("serialcode"),
                sizetypecode=data.get("sizetypecode", ""),
                ipaddress=data.get("ipaddress")
            )
            return JsonResponse({"status": "ok", "id": str(camera.id)})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})

    elif request.method == "GET":
        ipaddress = request.GET.get("ipaddress")
        if ipaddress:
            try:
                # ipaddress-аар шүүгээд хамгийн сүүлийн бичлэгийг авах
                camera = CameraData.objects.filter(ipaddress=ipaddress).order_by('-date').first()
                if camera:
                    data = {
                        "id": camera.id,
                        "container": camera.container,
                        "date": camera.date,
                        "ocrtime": camera.ocrtime,
                        "digitheight": camera.digitheight,
                        "left": camera.left,
                        "top": camera.top,
                        "right": camera.right,
                        "bottom": camera.bottom,
                        "confidencecode": camera.confidencecode,
                        "controldigit": camera.controldigit,
                        "numdigits": camera.numdigits,
                        "ownercity": camera.ownercity,
                        "ownercode": camera.ownercode,
                        "ownercompany": camera.ownercompany,
                        "readconfidence": camera.readconfidence,
                        "serialcode": camera.serialcode,
                        "sizetypecode": camera.sizetypecode,
                        "ipaddress":camera.ipaddress,
                    }
                    return JsonResponse(data)
                else:
                    return JsonResponse({"status": "error", "message": f"No CameraData found with container '{container}'"})
            except Exception as e:
                return JsonResponse({"status": "error", "message": str(e)})
        else:
            return JsonResponse({"status": "error", "message": "ipaddress parameter required"})

    return JsonResponse({"status": "error", "message": "Only GET or POST methods allowed"})

# TagReader API
class TagReaderView(APIView):
    def get(self, request):
        name = request.GET.get('name')  # ?name=... параметр авна
        if name:
            # name-аар шүүгээд хамгийн сүүлийн бичлэгийг авах
            tag = TagReader.objects.filter(name=name).order_by('-date').first()
            if tag:
                serializer = TagReaderSerializer(tag)
                return Response(serializer.data)
            else:
                return Response(
                    {"message": f"No TagReader found with name '{name}'"},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            # name параметр байхгүй бол бүх өгөгдлийг буцаана
            data = TagReader.objects.all().order_by('-date')
            serializer = TagReaderSerializer(data, many=True)
            return Response(serializer.data)

    def post(self, request):
        serializer = TagReaderSerializer(data=request.data)
        print('tag reader =====', request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
