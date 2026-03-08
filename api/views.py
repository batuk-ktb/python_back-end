from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import TagReader, CameraData, Transaction
from .serializers import TagReaderSerializer
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from .utils import save_container
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
                ipaddress=data.get("ipaddress"),
                plateImage=date.get("plateImage")
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
                        "plateImage":camera.plateImage
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
        ipaddress = request.GET.get('ipaddress')  # ?ipaddress=... параметр авна
        if ipaddress:
            # ipaddress-аар шүүгээд хамгийн сүүлийн бичлэгийг авах
            tag = TagReader.objects.filter(ipaddress=ipaddress).order_by('-date').first()
            if tag:
                serializer = TagReaderSerializer(tag)
                return Response(serializer.data)
            else:
                return Response(
                    {"message": f"No TagReader found with ipaddress '{ipaddress}'"},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            # ipaddress параметр байхгүй бол бүх өгөгдлийг буцаана
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

@csrf_exempt
def save_transaction(request):
    if request.method == "GET":
        page = int(request.GET.get("page", 1))
        puu_id = request.GET.get("puuId") 
        page_size = 10

        start = (page - 1) * page_size
        end = start + page_size

        qs = Transaction.objects.select_related(
            "conR1", "conL1", "conR2", "conL2", "conR3", "conL3", "conR4", "conL4"
        ).order_by("-created_at")
        if puu_id:
            qs = qs.filter(puuId=puu_id)
            
        total = qs.count()
        data = qs[start:end]

        result = []

        for t in data:
            item = {
                "id": t.id,
                "puuName": t.puuName,
                "puuId": t.puuId,
                "Weight": t.Weight,
                "tag_id": t.tag_id,
                "tag_date": t.tag_date.strftime("%Y-%m-%d %H:%M:%S") if t.tag_date else None,
                "created_at": t.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "containers": {}
            }

            # Loop through all 8 container fields
            for field_name in ["conR1", "conL1", "conR2", "conL2", "conR3", "conL3", "conR4", "conL4"]:
                container = getattr(t, field_name)
                if container:
                    item["containers"][field_name] = {
                        "id": container.id,
                        "container_id": container.container_id,
                        "date": container.date.strftime("%Y-%m-%d %H:%M:%S") if container.date else None,
                        "control_digit": container.control_digit,
                        "readconfidence": container.readconfidence,
                        "plateImage": container.plateImage
                    }
                else:
                    item["containers"][field_name] = None

            result.append(item)

        return JsonResponse({
            "transactions": result,
            "totalPages": (total + page_size - 1) // page_size,
        })
    elif request.method == "POST":
        try:
            body = json.loads(request.body)

            transaction = Transaction.objects.create(
                puuName=body.get("puuName"),
                puuId=body.get("puuId"),
                Weight=body.get("Weight"),

                tag_id=body.get("tag", {}).get("id"),
                tag_date=body.get("tag", {}).get("date"),

                conR1=save_container(body.get("conR1")),
                conL1=save_container(body.get("conL1")),
                conR2=save_container(body.get("conR2")),
                conL2=save_container(body.get("conL2")),
                conR3=save_container(body.get("conR3")),
                conL3=save_container(body.get("conL3")),
                conR4=save_container(body.get("conR4")),
                conL4=save_container(body.get("conL4")),
            )

            # ===== authentication logic =====
            authentication = 0

            if transaction.Weight > 1000:
                authentication = 1
            else:
                authentication = 2

            return JsonResponse({
                "success": True,
                "authentication": authentication,
                "id": transaction.id
            })

        except Exception as e:
            return JsonResponse({
                "success": False,
                "error": str(e)
            }, status=500)

    return JsonResponse({"error": "POST only"}, status=405)
