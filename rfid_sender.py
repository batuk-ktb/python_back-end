"""
Checks every 5 seconds: for non-LPR PUUs (Гаралт, Хяналт, Оролт, Пост groups),
if a new RFID tag date is seen → sends to SEND_URL and saves to carweight.SendRfid
"""

import time
import requests
from datetime import datetime, timezone
from pymongo import MongoClient

MONGO_URI      = "mongodb://localhost:27017/"
SEND_URL       = "http://10.1.1.193:3000/api/rfid"
CHECK_INTERVAL = 5
TARGET_GROUPS  = {"Гаралт", "Хяналт", "Оролт", "Пост"}


def load_last_sent(cw):
    result = {}
    try:
        for doc in cw["SendRfid"].aggregate([
            {"$sort": {"sentAt": -1}},
            {"$group": {"_id": "$scaleId", "rfidDate": {"$first": "$rfidDate"}}},
        ]):
            result[doc["_id"]] = {"rfid_date": doc.get("rfidDate")}
    except Exception as e:
        print(f"[RFID Sender] load_last_sent error: {e}", flush=True)
    return result


def main():
    print("[RFID Sender] Starting...", flush=True)

    _init_client = MongoClient(MONGO_URI)
    last_sent    = load_last_sent(_init_client["carweight"])
    _init_client.close()
    print(f"[RFID Sender] Loaded last_sent for {len(last_sent)} PUU(s) from DB", flush=True)

    while True:
        try:
            client = MongoClient(MONGO_URI)
            cw     = client["carweight"]
            mydb   = client["mydatabase"]

            puus = [
                p for p in cw["AllScales"].find()
                if p.get("rfid")
                and not p.get("lprEnabled")
                and p.get("group") in TARGET_GROUPS
            ]
            print(f"[Scan] {len(puus)} RFID PUU(s)", flush=True)

            for puu in puus:
                puu_id   = puu["id"]
                puu_name = puu.get("name", f"PUU {puu_id}")
                rfid_ip  = puu.get("rfid", "")

                tag_rec = mydb["api_tagreader"].find_one(
                    {"ipaddress": rfid_ip}, sort=[("date", -1)]
                ) if rfid_ip else None

                if not tag_rec or not tag_rec.get("tag"):
                    print(f"  [PUU {puu_id}] no tag for {rfid_ip} — skip", flush=True)
                    continue

                tag_value    = tag_rec["tag"]
                tag_raw_date = tag_rec.get("date")
                rfid_date_str = (
                    tag_raw_date.isoformat() if hasattr(tag_raw_date, "isoformat")
                    else str(tag_raw_date) if tag_raw_date else None
                )
                print(f"  [PUU {puu_id}] {puu_name}  Tag={tag_value!r}  date={rfid_date_str}", flush=True)

                prev         = last_sent.get(puu_id, {})
                rfid_changed = rfid_date_str != prev.get("rfid_date")
                if not rfid_changed:
                    print(f"  [PUU {puu_id}] skip — tag_new=False", flush=True)
                    continue

                # Read current weight from PuuWeight (written by poll_plc.py)
                weight_rec = cw["PuuWeight"].find_one({"scaleId": puu_id})
                weight     = weight_rec["weight"] if weight_rec and weight_rec.get("weight") is not None else 0.0
                print(f"  [PUU {puu_id}] Weight={weight}", flush=True)

                now     = datetime.now(timezone.utc)
                payload = {
                    "scaleId":    puu_id,
                    "scalename":  puu_name,
                    "tagValue":   tag_value,
                    "rfidDate":   rfid_date_str,
                    "weight":     weight,
                    "receivedAt": now.isoformat(),
                }

                response_text   = None
                response_status = 0
                try:
                    resp            = requests.post(SEND_URL, json=payload, timeout=5)
                    response_status = resp.status_code
                    response_text   = resp.text
                    print(f"  [PUU {puu_id}] SENT → {resp.status_code}  Tag={tag_value}", flush=True)
                except Exception as e:
                    response_text = str(e)
                    print(f"  [PUU {puu_id}] send failed: {e}", flush=True)

                try:
                    cw["SendRfid"].insert_one({
                        **payload,
                        "response": response_text,
                        "status":   response_status,
                        "sentAt":   now,
                    })
                    print(f"  [PUU {puu_id}] saved to SendRfid", flush=True)
                except Exception as e:
                    print(f"  [PUU {puu_id}] DB insert failed: {e}", flush=True)

                last_sent[puu_id] = {"rfid_date": rfid_date_str}

            client.close()

        except Exception as e:
            print(f"[ERROR] {e}", flush=True)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
