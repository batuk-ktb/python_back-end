import time
import struct
import json
import logging
import os
import requests
import django
from django.core.management.base import BaseCommand
from pymongo import MongoClient

logger = logging.getLogger(__name__)


POLL_INTERVAL = 1  # seconds
WEIGHT_URL = 'http://172.16.92.2:30511/read/3/{offset}/30'
WRITE_URL = 'http://172.16.92.2:30511/write'
TRIGGER_INDEX = 14  # 15th element (0-indexed)
LPR_LOG_DIR = 'D:/LPRlog'


def get_carweight_db():
    client = MongoClient('mongodb://localhost:27017/')
    return client['carweight']


def read_registers(puu_id):
    offset = (puu_id - 1) * 30
    url = WEIGHT_URL.format(offset=offset)
    resp = requests.get(url, timeout=5)
    data = resp.json()
    if not data:
        return None
    return data


def acknowledge_trigger(puu_id):
    reg_addr = (puu_id - 1) * 30 + TRIGGER_INDEX
    requests.post(WRITE_URL, json={'reg_addr': reg_addr, 'reg_value': 0}, timeout=5)


def parse_weight(data):
    reg1 = int(data[20])
    reg2 = int(data[21])
    weight = struct.unpack('<f', struct.pack('<HH', reg1, reg2))[0] * 10
    return round(weight, 2)


def read_lpr(lpr_ip):
    folder = os.path.join(LPR_LOG_DIR, lpr_ip)
    if not os.path.isdir(folder):
        return None
    files = sorted(
        [f for f in os.listdir(folder) if f.lower().endswith('.jpg')],
        reverse=True
    )
    if not files:
        return None
    latest = files[0]
    # Filename: 2026-04-07_14_47_ANPR-27-153-0083УЕС.jpg
    # Plate is the last segment after the final '-'
    plate = None
    if 'ANPR-' in latest:
        anpr_part = latest.replace('.jpg', '').split('ANPR-', 1)[-1]
        plate = anpr_part.split('-')[-1]
    return plate


def process_transaction(puu):
    from api.models import TagReader, CameraData, Container, Transaction, RemoteSyncLog

    CAM_TO_CON = {
        'cam1': 'conR1', 'cam2': 'conL1',
        'cam3': 'conR2', 'cam4': 'conL2',
        'cam5': 'conR3', 'cam6': 'conL3',
        'cam7': 'conR4', 'cam8': 'conL4',
    }

    puu_id = puu['id']
    puu_name = puu.get('name', '')

    # Read weight from PLC — retry up to 5 times if weight is 0 (PLC may not have updated registers yet)
    weight = 0.0
    for attempt in range(5):
        data = read_registers(puu_id)
        if data:
            weight = parse_weight(data)
        if weight != 0.0:
            break
        logger.warning(f"[PUU {puu_id}] Weight is 0 on attempt {attempt + 1}, retrying in 0.5s...")
        time.sleep(0.5)

    if weight == 0.0:
        logger.warning(f"[PUU {puu_id}] Weight still 0 after retries — skipping transaction.")
        return None

    # Get latest RFID tag
    rfid_ip = puu.get('rfid')
    tag = TagReader.objects.filter(ipaddress=rfid_ip).order_by('-date').first() if rfid_ip else None

    # Get latest camera data and create containers (only if containersEnabled)
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

    # Save Transaction
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

    # Read LPR plate from latest file if enabled
    lpr_plate = None
    if puu.get('lprEnabled', False):
        lpr_ip = puu.get('lpr', '')
        if lpr_ip:
            lpr_plate = read_lpr(lpr_ip)

    # Send to remote server and save to SendingData
    sent_data = {
        "puuId": puu_id,
        "puuName": puu_name,
        "Weight": weight,
        "tag": {
            "tag": tag.tag if tag else None,
            "date": tag.date.isoformat() if tag and tag.date else None,
        },
        "containers": containers_data,
        "lpr": lpr_plate,
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

    # Save directly via PyMongo to avoid djongo auto-id issue
    db = get_carweight_db()
    client = MongoClient('mongodb://localhost:27017/')
    client['carweight']['SendingData'].insert_one({
        'transaction_id': transaction.id,
        'sent_data': sent_data,
        'response_data': response_data,
        'status': sync_status,
    })

    logger.warning(f"[PUU {puu_id}] Transaction saved — Weight: {weight}, Tag: {tag.tag if tag else None}")
    return transaction


def start_poller():
    import traceback
    logger.warning("[PLC Poller] Starting...")
    db = get_carweight_db()
    puus = list(db['AllScales'].find())
    logger.warning(f"[PLC Poller] Found {len(puus)} PUUs. Polling every {POLL_INTERVAL}s...")

    # Initialize previous states — if already 1 on startup, process immediately
    prev_states = {}
    for puu in puus:
        try:
            data = read_registers(puu['id'])
            if not data:
                prev_states[puu['id']] = 0
                continue
            current = int(data[TRIGGER_INDEX])
            if current == 1:
                logger.warning(f"[PUU {puu['id']}] Already triggered on startup. Processing...")
                try:
                    process_transaction(puu)
                    acknowledge_trigger(puu['id'])
                    logger.warning(f"[PUU {puu['id']}] Acknowledged.")
                except Exception as e:
                    logger.warning(f"[PUU {puu['id']}] Startup process error: {traceback.format_exc()}")
            prev_states[puu['id']] = 0
        except Exception:
            logger.warning(f"[PUU {puu['id']}] Startup read error: {traceback.format_exc()}")
            prev_states[puu['id']] = 0

    heartbeat_counter = 0
    while True:
        heartbeat_counter += 1
        if heartbeat_counter % 10 == 0:
            logger.warning(f"[PLC Poller] Alive — tick {heartbeat_counter}")

        for puu in puus:
            puu_id = puu['id']
            try:
                data = read_registers(puu_id)
                if not data:
                    continue
                current = int(data[TRIGGER_INDEX])
                prev = prev_states[puu_id]

                if prev == 0 and current == 1:
                    logger.warning(f"[PUU {puu_id}] Trigger detected. Processing transaction...")
                    try:
                        process_transaction(puu)
                        acknowledge_trigger(puu_id)
                        logger.warning(f"[PUU {puu_id}] Acknowledged — wrote 0 back to PLC.")
                    except Exception as e:
                        logger.warning(f"[PUU {puu_id}] Error processing transaction: {e}")

                prev_states[puu_id] = current

            except Exception as e:
                logger.warning(f"[PUU {puu_id}] Poll error: {e}")

        time.sleep(POLL_INTERVAL)


class Command(BaseCommand):
    help = 'Poll PLC registers and trigger transaction when index 14 goes 0 -> 1'

    def handle(self, *args, **options):
        start_poller()
