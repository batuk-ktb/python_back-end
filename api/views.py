from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import TagReader, CameraData, Transaction, Container
from .serializers import TagReaderSerializer
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from pymongo import MongoClient
import requests
import struct
import json

CAM_TO_CON = {
    'cam1': 'conR1',
    'cam2': 'conL1',
    'cam3': 'conR2',
    'cam4': 'conL2',
    'cam5': 'conR3',
    'cam6': 'conL3',
    'cam7': 'conR4',
    'cam8': 'conL4',
}

def get_carweight_db():
    client = MongoClient('mongodb://localhost:27017/')
    return client['carweight']

def read_weight(puu_id):
    offset = (puu_id - 1) * 30
    url = f'http://172.16.92.2:30511/read/3/{offset}/30'
    resp = requests.get(url, timeout=5)
    data = resp.json()
    if not data:
        return 0.0
    reg1 = int(data[20])
    reg2 = int(data[21])
    # Two 16-bit registers as little-endian 32-bit float, scaled by 10
    weight = struct.unpack('<f', struct.pack('<HH', reg1, reg2))[0] * 10
    return round(weight, 2)

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
                plateImage=data.get("plateimage")
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

        qs = Transaction.objects.all().order_by("-created_at")
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
            print('t value', t.__dict__)

            print('r1,', getattr(t, 'conR1_id'))
            print('l1,', getattr(t, 'conL1_id'))
            print("R1:", t.conR1_id, t.conR1)
            print("L1:", t.conL1_id, t.conL1)

            print("Transaction FK:", t.conR1_id)

            print("Container exists:", Container.objects.filter(id=t.conR1_id).exists())

            print("Container:", Container.objects.filter(id=t.conR1_id).first())
            print("Container exists:", Container.objects.filter(id=t.conL1_id).exists())

            print("Container:", Container.objects.filter(id=t.conL1_id).first())
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
            puu_id = body.get("puuId")
            weight = read_weight(puu_id)

            # 1. Look up PUU from carweight.AllScales
            db = get_carweight_db()
            puu = db['AllScales'].find_one({'id': puu_id})
            if not puu:
                return JsonResponse({"success": False, "error": f"PUU {puu_id} not found"}, status=404)

            puu_name = puu.get('name', '')

            # 2. Get latest RFID tag using rfid IP
            rfid_ip = puu.get('rfid')
            tag = TagReader.objects.filter(ipaddress=rfid_ip).order_by('-date').first() if rfid_ip else None

            # 3. Get latest camera data for each cam, create Container objects (only if containersEnabled)
            containers = {}
            containers_data = {}
            if puu.get('containersEnabled', False):
                for cam_key, con_key in CAM_TO_CON.items():
                    cam_ip = puu.get(cam_key)
                    if cam_ip:
                        cam = CameraData.objects.filter(ipaddress=cam_ip).order_by('-date').first()
                        if cam:
                            container = Container.objects.create(
                                container_id=cam.container,
                                date=cam.date,
                                control_digit=cam.controldigit,
                                readconfidence=float(cam.readconfidence) if cam.readconfidence else None,
                                plateImage=cam.plateImage,
                            )
                            containers[con_key] = container
                            containers_data[con_key] = {
                                "container": cam.container,
                                "date": cam.date.isoformat() if cam.date else None,
                                "controldigit": cam.controldigit,
                                "readconfidence": cam.readconfidence,
                                "plateImage": cam.plateImage,
                            }
                        else:
                            containers[con_key] = None
                            containers_data[con_key] = None
                    else:
                        containers[con_key] = None
                        containers_data[con_key] = None

            # 4. Create Transaction
            transaction = Transaction.objects.create(
                puuName=puu_name,
                puuId=puu_id,
                Weight=weight,
                tag_id=tag.tag if tag else None,
                tag_date=tag.date if tag else None,
                conR1=containers.get('conR1'),
                conL1=containers.get('conL1'),
                conR2=containers.get('conR2'),
                conL2=containers.get('conL2'),
                conR3=containers.get('conR3'),
                conL3=containers.get('conL3'),
                conR4=containers.get('conR4'),
                conL4=containers.get('conL4'),
            )

            # 5. Build sent_data and save to SendingData
            sent_data = {
                "puuId": puu_id,
                "puuName": puu_name,
                "Weight": weight,
                "tag": {
                    "tag": tag.tag if tag else None,
                    "date": tag.date.isoformat() if tag and tag.date else None,
                },
                "containers": containers_data,
            }
            try:
                remote_resp = requests.post(
                    'http://172.16.92.5/',
                    json=sent_data,
                    timeout=5,
                )
                response_data = remote_resp.text
                sync_status = 'success'
            except Exception as e:
                response_data = str(e)
                sync_status = 'error'

            MongoClient('mongodb://localhost:27017/')['carweight']['SendingData'].insert_one({
                'transaction_id': transaction.id,
                'sent_data': sent_data,
                'response_data': response_data,
                'status': sync_status,
            })

            authentication = 1 if transaction.Weight > 1000 else 2

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
