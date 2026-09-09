import time
import struct
import json
import logging
import traceback
import requests
import django
from datetime import datetime, timezone, timedelta

FRESH_MINUTES = 10

def is_fresh(dt):
    if not dt:
        return False
    try:
        now = datetime.now(timezone.utc)
        if isinstance(dt, str):
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M',
                        '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ'):
                try:
                    dt = datetime.strptime(dt, fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
            else:
                return False
        if hasattr(dt, 'tzinfo') and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (now - dt) < timedelta(minutes=FRESH_MINUTES)
    except Exception:
        return False
from django.core.management.base import BaseCommand
from pymongo import MongoClient

logger = logging.getLogger(__name__)


POLL_INTERVAL  = 1   # seconds — WeightOk polling
LPR_CHECK_SECS = 5   # seconds — LPR/tag freshness check interval
SEND_URL       = 'http://10.1.1.193:3000/api/scale/1'
WEIGHT_URL     = 'http://172.16.92.2:30511/read/3/{offset}/30'
WRITE_URL      = 'http://172.16.92.2:30511/write'
TRIGGER_INDEX  = 14


def get_carweight_db():
    client = MongoClient('mongodb://localhost:27017/')
    return client['carweight']


def read_registers(puu_id):
    offset = (puu_id - 1) * 30
    url = WEIGHT_URL.format(offset=offset)
    try:
        resp = requests.get(url, timeout=5)
        if not resp.ok or not resp.text.strip():
            return None
        data = resp.json()
        return data if data else None
    except Exception:
        return None


def acknowledge_trigger(puu_id):
    reg_addr = (puu_id - 1) * 30 + TRIGGER_INDEX
    requests.post(WRITE_URL, json={'reg_addr': reg_addr, 'reg_value': 0}, timeout=5)


def parse_weight(data):
    reg1 = int(data[20])
    reg2 = int(data[21])
    weight = struct.unpack('<f', struct.pack('<HH', reg1, reg2))[0] * 10
    return round(weight, 2)


def read_lpr_with_image(lpr_ip):
    """Return (plate, date_str, datetime, filepath) from latest LPR log file."""
    import os, re as _re
    folder = os.path.join("D:\\LPRlog", lpr_ip)
    if not os.path.isdir(folder):
        return None, None, None, None
    files = sorted(
        [f for f in os.listdir(folder) if f.lower().endswith('.jpg')],
        reverse=True
    )
    for filename in files:
        m = _re.match(
            r'^(\d{4}-\d{2}-\d{2})_(\d{2})_(\d{2})_ANPR-\d+-\d+-(.+)\.jpg$',
            filename, _re.IGNORECASE
        )
        if m and m.group(4).lower() != 'unlicensed':
            plate    = m.group(4)
            date_str = f"{m.group(1)} {m.group(2)}:{m.group(3)}"
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M')
            except Exception:
                dt = None
            filepath = os.path.join(folder, filename)
            return plate, date_str, dt, filepath
    return None, None, None, None


def read_lpr(lpr_ip):
    """Return (plate, date_str, datetime) from latest D:\\LPRlog\\{lpr_ip}\\*.jpg file."""
    import os, re as _re
    folder = os.path.join("D:\\LPRlog", lpr_ip)
    if not os.path.isdir(folder):
        return None, None, None
    files = sorted(
        [f for f in os.listdir(folder) if f.lower().endswith('.jpg')],
        reverse=True
    )
    for filename in files:
        m = _re.match(
            r'^(\d{4}-\d{2}-\d{2})_(\d{2})_(\d{2})_ANPR-\d+-\d+-(.+)\.jpg$',
            filename, _re.IGNORECASE
        )
        if m and m.group(4).lower() != 'unlicensed':
            plate    = m.group(4)
            date_str = f"{m.group(1)} {m.group(2)}:{m.group(3)}"
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M')
            except Exception:
                dt = None
            return plate, date_str, dt
    return None, None, None


def send_lpr_data(puu, lpr_last_sent: dict):
    """Called on WeightOk rising edge. Sends LPR+tag to 10.1.1.193 if both fresh and new."""
    puu_id  = puu['id']
    lpr_ip  = puu.get('lpr', '')
    rfid_ip = puu.get('rfid', '')

    if not lpr_ip:
        print(f"  [LPR PUU {puu_id}] no lpr_ip configured", flush=True)
        return

    # Read LPR from file
    lpr_plate, lpr_date_str, lpr_dt = read_lpr(lpr_ip)
    print(f"  [LPR PUU {puu_id}] plate={lpr_plate!r}  date={lpr_date_str}  age={_age_secs(lpr_dt):.0f}s", flush=True)
    if not lpr_plate:
        return
    if _age_secs(lpr_dt) > FRESH_MINUTES * 60:
        print(f"  [LPR PUU {puu_id}] LPR stale — skip", flush=True)
        return

    # Read tag from DB
    try:
        client  = MongoClient('mongodb://localhost:27017/')
        tag_rec = client['mydatabase']['api_tagreader'].find_one(
            {'ipaddress': rfid_ip}, sort=[('date', -1)]
        ) if rfid_ip else None
        client.close()
    except Exception as e:
        print(f"  [LPR PUU {puu_id}] tag DB error: {e}", flush=True)
        return

    if not tag_rec or not tag_rec.get('tag'):
        print(f"  [LPR PUU {puu_id}] no tag record for rfid_ip={rfid_ip!r}", flush=True)
        return

    tag_value     = tag_rec['tag']
    tag_raw_date  = tag_rec.get('date')
    rfid_date_str = tag_raw_date.isoformat() if hasattr(tag_raw_date, 'isoformat') else str(tag_raw_date) if tag_raw_date else None
    print(f"  [LPR PUU {puu_id}] tag={tag_value!r}  date={rfid_date_str}  age={_age_secs(tag_raw_date):.0f}s", flush=True)

    if _age_secs(tag_raw_date) > FRESH_MINUTES * 60:
        print(f"  [LPR PUU {puu_id}] tag stale — skip", flush=True)
        return

    # Duplicate check
    prev = lpr_last_sent.get(puu_id, {})
    if lpr_date_str == prev.get('lpr_date') and rfid_date_str == prev.get('rfid_date'):
        print(f"  [LPR PUU {puu_id}] duplicate — skip", flush=True)
        return

    payload = {
        'scaleId':   puu_id,
        'lprNumber': lpr_plate,
        'lprDate':   lpr_date_str,
        'tagValue':  tag_value,
        'rfidDate':  rfid_date_str,
    }

    try:
        resp = requests.post(SEND_URL, json=payload, timeout=5)
        print(f"  [LPR PUU {puu_id}] SENT → {resp.status_code}  LPR={lpr_plate}  Tag={tag_value}", flush=True)
    except Exception as e:
        print(f"  [LPR PUU {puu_id}] send failed: {e}", flush=True)

    try:
        _c = MongoClient('mongodb://localhost:27017/')
        _c['carweight']['SendingData1'].insert_one({**payload, 'sentAt': datetime.now(timezone.utc)})
        _c.close()
        print(f"  [LPR PUU {puu_id}] saved to SendingData1", flush=True)
    except Exception as e:
        print(f"  [LPR PUU {puu_id}] DB insert failed: {e}", flush=True)

    lpr_last_sent[puu_id] = {'lpr_date': lpr_date_str, 'rfid_date': rfid_date_str}


def process_transaction(puu, last_sent: dict, cleared_at=None, cam_baseline_data=None):
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

    logger.warning(f"[PUU {puu_id}] Weight={weight}")

    if weight == 0.0:
        logger.warning(f"[PUU {puu_id}] Weight still 0 after retries — skipping transaction.")
        return None

    # Get latest RFID tag — must be read AFTER the previous truck left (cleared_at).
    # Exclude records with empty tag field: the RFID device can push "tag_event" payloads with
    # an empty EPC (read errors) which would become the newest record and hide the real tag.
    rfid_ip = puu.get('rfid')
    tag = (TagReader.objects
           .filter(ipaddress=rfid_ip)
           .exclude(tag='')
           .order_by('-date')
           .first()) if rfid_ip else None
    if tag and cleared_at:
        # api_tagreader stores local time (UTC+8) as if UTC — strip tzinfo to get naive local time
        tag_dt = tag.date.replace(tzinfo=None) if tag.date and hasattr(tag.date, 'tzinfo') and tag.date.tzinfo else tag.date
        if tag_dt and tag_dt < cleared_at:
            logger.warning(f"[PUU {puu_id}] RFID tag {tag.tag!r} date {tag_dt} is before cleared_at {cleared_at} — rejecting stale tag")
            tag = None
    logger.warning(f"[PUU {puu_id}] rfid_ip={rfid_ip!r}  tag={tag.tag if tag else None}")

    # Read LPR plate + date from latest file if enabled
    lpr_plate    = None
    lpr_date     = None
    lpr_raw_date = None
    lpr_enabled  = puu.get('lprEnabled', False)
    lpr_ip       = puu.get('lpr', '')
    logger.warning(f"[PUU {puu_id}] lprEnabled={lpr_enabled!r}  lpr_ip={lpr_ip!r}")
    lpr_snap_id = None
    lpr_filepath = None
    if lpr_enabled and lpr_ip:
        lpr_plate, lpr_date, lpr_raw_date, lpr_filepath = read_lpr_with_image(lpr_ip)
    logger.warning(f"[PUU {puu_id}] lpr_plate={lpr_plate!r}  lpr_date={lpr_date!r}")

    now_local     = datetime.now()
    now_utc       = datetime.now(timezone.utc)
    rfid_date_str = tag.date.isoformat() if tag and tag.date else None

    # Save LPR image to LprPictures now that we also have RFID data
    if lpr_plate and lpr_filepath:
        try:
            import base64 as _b64
            with open(lpr_filepath, 'rb') as f:
                img_b64 = _b64.b64encode(f.read()).decode('utf-8')
            _c = MongoClient('mongodb://localhost:27017/')
            result = _c['carweight']['LprPictures'].insert_one({
                'lprNumber':  lpr_plate,
                'lprDate':    lpr_date,
                'plateImage': img_b64,
                'puuId':      puu_id,
                'tagValue':   tag.tag if tag else None,
                'rfidDate':   rfid_date_str,
                'createdAt':  now_utc,
            })
            lpr_snap_id = str(result.inserted_id)
            _c.close()
        except Exception as e:
            logger.warning(f"[PUU {puu_id}] LprPictures insert failed: {e}")

    def _age_seconds(d):
        """Return age of d in seconds relative to now_local. Returns large number if unknown."""
        if d is None:
            return 999999
        try:
            if isinstance(d, str):
                for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M',
                            '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ'):
                    try:
                        d = datetime.strptime(d, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    return 999999
            if hasattr(d, 'tzinfo') and d.tzinfo is not None:
                d = d.replace(tzinfo=None)
            return abs((now_local - d).total_seconds())
        except Exception:
            return 999999

    lpr_age   = _age_seconds(lpr_raw_date)
    tag_age   = _age_seconds(tag.date if tag else None)
    lpr_fresh = lpr_age < FRESH_MINUTES * 60
    tag_fresh = tag_age < FRESH_MINUTES * 60
    both_fresh = lpr_fresh and tag_fresh

    logger.warning(f"[PUU {puu_id}] lpr_age={lpr_age:.0f}s  tag_age={tag_age:.0f}s  lpr_fresh={lpr_fresh}  tag_fresh={tag_fresh}")

    # Compare against last sent dates — only send if dates actually changed
    prev = last_sent.get(puu_id, {})
    dates_changed = (lpr_date != prev.get('lpr_date')) or (rfid_date_str != prev.get('rfid_date'))

    # Determine skip reason for frontend visibility
    if not lpr_plate:       skip_reason = "no_lpr"
    elif not tag:           skip_reason = "no_tag"
    elif not lpr_fresh:     skip_reason = "lpr_stale"
    elif not tag_fresh:     skip_reason = "tag_stale"
    elif not dates_changed: skip_reason = "duplicate"
    elif not lpr_enabled:   skip_reason = "lpr_disabled"
    else:                   skip_reason = None

    # Always upsert WeightOkData so frontend can see current state + skip reason
    try:
        _client = MongoClient('mongodb://localhost:27017/')
        _client['carweight']['WeightOkData'].update_one(
            {'puuId': puu_id},
            {'$set': {
                'puuId':       puu_id,
                'lprNumber':   lpr_plate,
                'lprDate':     lpr_date,
                'lprFresh':    lpr_fresh,
                'tagValue':    tag.tag if tag else None,
                'rfidDate':    rfid_date_str,
                'tagFresh':    tag_fresh,
                'bothFresh':   both_fresh,
                'sent':        skip_reason is None,
                'skipReason':  skip_reason,
                'triggeredAt': now_utc,
            }},
            upsert=True,
        )
        _client.close()
    except Exception as e:
        logger.warning(f"[PUU {puu_id}] WeightOkData upsert failed: {e}")

    print(f"[PUU {puu_id}] skip_reason={skip_reason!r}  lpr={lpr_plate!r}  tag={tag.tag if tag else None!r}  lpr_age={lpr_age:.0f}s  tag_age={tag_age:.0f}s  dates_changed={dates_changed}", flush=True)

    if skip_reason is None:
        scale_payload = {
            'scaleId':   puu_id,
            'lprNumber': lpr_plate,
            'lprDate':   lpr_date,
            'tagValue':  tag.tag if tag else None,
            'rfidDate':  rfid_date_str,
        }
        try:
            requests.post(
                'http://10.1.1.193:3000/api/scale/1',
                json=scale_payload,
                timeout=5,
            )
            logger.warning(f"[PUU {puu_id}] Sent to 10.1.1.193 — LPR: {lpr_plate}, Tag: {tag.tag if tag else None}")
        except Exception as e:
            logger.warning(f"[PUU {puu_id}] 10.1.1.193 send failed: {e}")
        try:
            _client = MongoClient('mongodb://localhost:27017/')
            _client['carweight']['SendingData1'].insert_one({
                **scale_payload,
                'sentAt': now_utc,
            })
            _client.close()
            logger.warning(f"[PUU {puu_id}] Saved to SendingData1")
        except Exception as e:
            logger.warning(f"[PUU {puu_id}] SendingData1 insert failed: {traceback.format_exc()}")

        last_sent[puu_id] = {'lpr_date': lpr_date, 'rfid_date': rfid_date_str}
    else:
        logger.warning(f"[PUU {puu_id}] Send skipped: {skip_reason}")

    # Get latest camera data and create containers (only if containersEnabled)
    containers = {}
    containers_data = {}
    if puu.get('containersEnabled', False):
        for cam_key, con_key in CAM_TO_CON.items():
            cam_ip = puu.get(cam_key)
            if cam_ip:
                cam = CameraData.objects.filter(ipaddress=cam_ip).order_by('-date').first()
                if cam:
                    baseline_date = (cam_baseline_data or {}).get(cam_ip)
                    # Include only if no baseline (first truck) or date changed since last clear
                    is_new = baseline_date is None or cam.date != baseline_date
                    if is_new:
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
            else:
                containers[con_key] = None
                containers_data[con_key] = None

    # Try saving Django Transaction — failure is non-fatal
    transaction_id = None
    try:
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
        transaction_id = transaction.id
    except Exception:
        logger.warning(f"[PUU {puu_id}] Transaction.objects.create failed:\n{traceback.format_exc()}")

    # Build sent_data and save to SendingData regardless of ORM result
    # Use tag if it passed the cleared_at guard (tag is already None if stale vs previous truck).
    # Do NOT additionally filter by tag_fresh here — a truck queuing >10 min would lose its RFID.
    # tag_fresh is kept for the SendingData1 / remote-send logic above, but not for the main record.
    # Also guard tag.tag itself — RFID device can push a record with empty/null tag field
    # (e.g. on reconnect events); that record is a TagReader object but tag.tag is falsy.
    tag_for_save = None
    if tag and tag.tag:
        tag_for_save = {
            "tag": tag.tag,
            "date": tag.date.isoformat() if tag.date else None,
        }

    sent_data = {
        "puuId": puu_id,
        "puuName": puu_name,
        "Weight": weight,
        "tag": tag_for_save,
        "containers": containers_data,
        "lpr": lpr_plate,
        "lpr_date": lpr_date,
        "lprSnapId": lpr_snap_id,
    }

    # Insert to SendingData BEFORE the remote HTTP call so that bg-poller.ts's
    # 15-second dedup window always finds this record and skips its own insert.
    sending_data_id = None
    try:
        _c = MongoClient('mongodb://localhost:27017/')
        result = _c['carweight']['SendingData'].insert_one({
            'transaction_id': transaction_id,
            'puuId':          puu_id,
            'sent_data':      sent_data,
            'response_data':  '',
            'status':         'pending',
        })
        sending_data_id = result.inserted_id
        _c.close()
        logger.warning(f"[PUU {puu_id}] Saved to SendingData — Weight: {weight}, Tag: {tag.tag if tag else None}")
    except Exception:
        logger.warning(f"[PUU {puu_id}] SendingData insert failed:\n{traceback.format_exc()}")

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

    # Update the record with the final response now that the remote call finished
    if sending_data_id is not None:
        try:
            _c = MongoClient('mongodb://localhost:27017/')
            _c['carweight']['SendingData'].update_one(
                {'_id': sending_data_id},
                {'$set': {'response_data': response_data, 'status': sync_status}},
            )
            _c.close()
        except Exception:
            pass


def _age_secs(dt):
    """Seconds since dt. Returns large number if unknown or unparseable."""
    if dt is None:
        return 999999
    try:
        now = datetime.now()
        if isinstance(dt, str):
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M',
                        '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ'):
                try:
                    dt = datetime.strptime(dt, fmt); break
                except ValueError:
                    continue
            else:
                return 999999
        if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return abs((now - dt).total_seconds())
    except Exception:
        return 999999




def start_poller():
    import traceback
    print("[PLC Poller] Starting...", flush=True)
    db = get_carweight_db()
    puus = list(db['AllScales'].find())
    lpr_puus = [p for p in puus if p.get('lprEnabled')]
    print(f"[PLC Poller] Found {len(puus)} PUUs ({len(lpr_puus)} LPR-enabled). Polling every {POLL_INTERVAL}s...", flush=True)
    for p in lpr_puus:
        print(f"  LPR PUU: id={p['id']} name={p.get('name')} lpr_ip={p.get('lpr')}", flush=True)

    last_sent: dict = {}
    weight_zero_at: dict = {}  # puuId → datetime when weight last went to 0
    cam_baseline: dict = {}    # puuId → {cam_ip: date} snapshot at last clear

    # Seed weight_zero_at from the last SendingData record so the cleared_at guard
    # works correctly on the first truck after a restart.
    # ObjectId.generation_time is UTC; convert to local (UTC+8) to match datetime.now().
    for _puu in puus:
        _pid = _puu['id']
        try:
            _last = db['SendingData'].find_one({'puuId': _pid}, sort=[('_id', -1)])
            if _last:
                _utc_ts = _last['_id'].generation_time  # tz-aware UTC
                _local_ts = _utc_ts.replace(tzinfo=None) + timedelta(hours=8)
                weight_zero_at[_pid] = _local_ts
                print(f"[PUU {_pid}] Init weight_zero_at → {_local_ts} (from last SendingData)", flush=True)
            else:
                weight_zero_at[_pid] = datetime.now()
                print(f"[PUU {_pid}] Init weight_zero_at → now (no previous records)", flush=True)
        except Exception as _e:
            weight_zero_at[_pid] = datetime.now()
            print(f"[PUU {_pid}] Init weight_zero_at → now (error: {_e})", flush=True)

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
                    process_transaction(puu, last_sent, weight_zero_at.get(puu['id']), cam_baseline.get(puu['id']))
                    acknowledge_trigger(puu['id'])
                    logger.warning(f"[PUU {puu['id']}] Acknowledged.")
                except Exception as e:
                    logger.warning(f"[PUU {puu['id']}] Startup process error: {traceback.format_exc()}")
            prev_states[puu['id']] = current
        except Exception:
            logger.warning(f"[PUU {puu['id']}] Startup read error: {traceback.format_exc()}")
            prev_states[puu['id']] = 0

    heartbeat_counter = 0
    while True:
        heartbeat_counter += 1
        if heartbeat_counter % 10 == 0:
            print(f"[PLC Poller] Alive — tick {heartbeat_counter}", flush=True)

        for puu in puus:
            puu_id = puu['id']
            try:
                data = read_registers(puu_id)
                if not data:
                    continue
                current = int(data[TRIGGER_INDEX])
                prev = prev_states[puu_id]

                # Store current weight for rfid_sender
                try:
                    w = parse_weight(data)
                    db['PuuWeight'].update_one(
                        {'scaleId': puu_id},
                        {'$set': {'scaleId': puu_id, 'weight': w, 'updatedAt': datetime.now(timezone.utc)}},
                        upsert=True,
                    )
                except Exception:
                    pass

                if prev == 1 and current == 0:
                    # Falling edge — record clear time and snapshot camera dates
                    weight_zero_at[puu_id] = datetime.now()
                    print(f"[PUU {puu_id}] Weight cleared at {weight_zero_at[puu_id]}", flush=True)
                    if puu.get('containersEnabled'):
                        try:
                            from api.models import CameraData
                            cam_baseline[puu_id] = {}
                            for cam_key in ['cam1','cam2','cam3','cam4','cam5','cam6','cam7','cam8']:
                                cam_ip = puu.get(cam_key)
                                if cam_ip:
                                    cam = CameraData.objects.filter(ipaddress=cam_ip).order_by('-date').first()
                                    cam_baseline[puu_id][cam_ip] = cam.date if cam else None
                            print(f"[PUU {puu_id}] Camera baseline snapshot taken", flush=True)
                        except Exception as e:
                            print(f"[PUU {puu_id}] Baseline snapshot error: {e}", flush=True)
                            cam_baseline[puu_id] = {}

                if prev == 0 and current == 1:
                    print(f"[PUU {puu_id}] WeightOk trigger detected!", flush=True)
                    try:
                        process_transaction(puu, last_sent, weight_zero_at.get(puu_id), cam_baseline.get(puu_id))
                        acknowledge_trigger(puu_id)
                        print(f"[PUU {puu_id}] Acknowledged.", flush=True)
                    except Exception as e:
                        print(f"[PUU {puu_id}] ERROR:\n{traceback.format_exc()}", flush=True)

                prev_states[puu_id] = current

            except Exception as e:
                logger.warning(f"[PUU {puu_id}] Poll error: {e}")

        time.sleep(POLL_INTERVAL)


class Command(BaseCommand):
    help = 'Poll PLC registers and trigger transaction when index 14 goes 0 -> 1'

    def handle(self, *args, **options):
        start_poller()
