from django.shortcuts import render

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .models import CameraData

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

            return JsonResponse({"status": "ok", "id": camera.id})

        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})
    else:
        return JsonResponse({"status": "error", "message": "POST method required"})
