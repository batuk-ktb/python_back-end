"""
Checks every 5 seconds: if both LPR and RFID tag have new dates → sends to
10.1.1.193 and saves to SendingData1.

Run:  python lpr_sender.py
"""

import os
import re
import time
import requests
from datetime import datetime, timezone
from pymongo import MongoClient

MONGO_URI      = "mongodb://localhost:27017/"
LPR_BASE       = "D:\\LPRlog"
SEND_URL       = "http://10.1.1.193:3000/api/scale/1"
CHECK_INTERVAL = 5


def read_lpr(lpr_ip):
    folder = os.path.join(LPR_BASE, lpr_ip)
    if not os.path.isdir(folder):
        return None, None
    files = sorted(
        [f for f in os.listdir(folder) if f.lower().endswith('.jpg')],
        reverse=True
    )
    for filename in files:
        m = re.match(
            r'^(\d{4}-\d{2}-\d{2})_(\d{2})_(\d{2})_ANPR-\d+-\d+-(.+)\.jpg$',
            filename, re.IGNORECASE
        )
        if m and m.group(4).lower() != 'unlicensed':
            plate    = m.group(4)
            date_str = f"{m.group(1)} {m.group(2)}:{m.group(3)}"
            return plate, date_str
    return None, None


def load_last_sent(cw):
    """Read the most recent sent record per PUU from SendingData1."""
    result = {}
    try:
        for doc in cw['SendingData1'].aggregate([
            {"$sort": {"sentAt": -1}},
            {"$group": {"_id": "$scaleId", "lprDate": {"$first": "$lprDate"}, "rfidDate": {"$first": "$rfidDate"}}},
        ]):
            result[doc['_id']] = {'lpr_date': doc.get('lprDate'), 'rfid_date': doc.get('rfidDate')}
    except Exception as e:
        print(f"[LPR Sender] load_last_sent error: {e}", flush=True)
    return result


def main():
    print("[LPR Sender] Starting...", flush=True)

    # Load last sent dates from DB so restarts don't re-send the same data
    _init_client = MongoClient(MONGO_URI)
    last_sent    = load_last_sent(_init_client['carweight'])
    _init_client.close()
    print(f"[LPR Sender] Loaded last_sent for {len(last_sent)} PUU(s) from DB", flush=True)

    while True:
        try:
            client   = MongoClient(MONGO_URI)
            cw       = client['carweight']
            mydb     = client['mydatabase']
            lpr_puus = [p for p in cw['AllScales'].find() if p.get('lprEnabled')]
            print(f"[Scan] {len(lpr_puus)} LPR-enabled PUU(s)", flush=True)

            for puu in lpr_puus:
                puu_id  = puu['id']
                lpr_ip  = puu.get('lpr', '')
                rfid_ip = puu.get('rfid', '')

                # LPR
                lpr_plate, lpr_date_str = read_lpr(lpr_ip)
                print(f"  [PUU {puu_id}] LPR={lpr_plate!r}  date={lpr_date_str}", flush=True)
                if not lpr_plate:
                    cw['LprStatus'].update_one({'scaleId': puu_id}, {'$set': {'scaleId': puu_id, 'lprNumber': None, 'lprDate': None, 'tagValue': None, 'rfidDate': None, 'updatedAt': datetime.now(timezone.utc)}}, upsert=True)
                    continue

                # Tag
                tag_rec       = mydb['api_tagreader'].find_one(
                    {'ipaddress': rfid_ip}, sort=[('date', -1)]
                ) if rfid_ip else None
                tag_value     = tag_rec['tag'] if tag_rec and tag_rec.get('tag') else None
                tag_raw_date  = tag_rec.get('date') if tag_rec else None
                rfid_date_str = tag_raw_date.isoformat() if hasattr(tag_raw_date, 'isoformat') else str(tag_raw_date) if tag_raw_date else None
                print(f"  [PUU {puu_id}] Tag={tag_value!r}  date={rfid_date_str}", flush=True)

                # Always update LprStatus for frontend display (even if tag missing)
                try:
                    cw['LprStatus'].update_one(
                        {'scaleId': puu_id},
                        {'$set': {'scaleId': puu_id, 'lprNumber': lpr_plate, 'lprDate': lpr_date_str, 'tagValue': tag_value, 'rfidDate': rfid_date_str, 'updatedAt': datetime.now(timezone.utc)}},
                        upsert=True,
                    )
                except Exception as e:
                    print(f"  [PUU {puu_id}] LprStatus update failed: {e}", flush=True)

                if not tag_value:
                    print(f"  [PUU {puu_id}] no tag for {rfid_ip} — skip", flush=True)
                    continue

                # Both dates must be new — if either hasn't changed, skip
                prev         = last_sent.get(puu_id, {})
                lpr_changed  = lpr_date_str  != prev.get('lpr_date')
                rfid_changed = rfid_date_str != prev.get('rfid_date')
                if not lpr_changed or not rfid_changed:
                    print(f"  [PUU {puu_id}] skip — lpr_new={lpr_changed} tag_new={rfid_changed}", flush=True)
                    continue

                payload = {
                    'scaleId':   puu_id,
                    'lprNumber': lpr_plate,
                    'lprDate':   lpr_date_str,
                    'tagValue':  tag_value,
                    'rfidDate':  rfid_date_str,
                }

                response_text   = None
                response_status = 0
                try:
                    resp            = requests.post(SEND_URL, json=payload, timeout=5)
                    response_status = resp.status_code
                    response_text   = resp.text
                    print(f"  [PUU {puu_id}] SENT → {resp.status_code}  LPR={lpr_plate}  Tag={tag_value}", flush=True)
                except Exception as e:
                    response_text = str(e)
                    print(f"  [PUU {puu_id}] send failed: {e}", flush=True)

                try:
                    cw['SendingData1'].insert_one({
                        **payload,
                        'response': response_text,
                        'status':   response_status,
                        'sentAt':   datetime.now(timezone.utc),
                    })
                    print(f"  [PUU {puu_id}] saved to SendingData1", flush=True)
                except Exception as e:
                    print(f"  [PUU {puu_id}] DB insert failed: {e}", flush=True)

                last_sent[puu_id] = {'lpr_date': lpr_date_str, 'rfid_date': rfid_date_str}

            client.close()

        except Exception as e:
            print(f"[ERROR] {e}", flush=True)

        time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    main()
