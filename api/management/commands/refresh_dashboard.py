"""
Hourly background job: aggregates DashboardData and upserts results
into DashboardStats collection in MongoDB.

Run once:   python manage.py refresh_dashboard
Run hourly: python manage.py refresh_dashboard --loop
"""

import time
import logging
from datetime import datetime, timedelta, timezone

from pymongo import MongoClient
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

MONGO_URI  = "mongodb://localhost:27017/"
DB_NAME    = "carweight"
INTERVAL   = 3600  # seconds

GROUP_LABEL: dict[int, str] = {}
for _i in range(1,  6):  GROUP_LABEL[_i] = "Оролт"
for _i in range(6,  11): GROUP_LABEL[_i] = "Гаралт"
for _i in range(11, 19): GROUP_LABEL[_i] = "Хяналт"

RANGES: dict[str, timedelta | None] = {
    "day":   timedelta(days=1),
    "week":  timedelta(weeks=1),
    "month": timedelta(days=30),
    "all":   None,
}


def _compute(source, range_key: str) -> dict:
    delta = RANGES[range_key]
    from_dt = (datetime.now(timezone.utc) - delta) if delta else datetime(1970, 1, 1, tzinfo=timezone.utc)

    pipeline: list = []
    if delta:
        pipeline.append({"$match": {"createdAt": {"$gte": from_dt}}})
    pipeline += [
        {
            "$group": {
                "_id":       "$puuId",
                "puuName":   {"$last": "$puuName"},
                "count":     {"$sum": 1},
                "avgWeight": {"$avg": "$weight"},
            }
        },
        {"$sort": {"_id": 1}},
    ]

    by_scale = []
    group_totals = {"Оролт": 0, "Гаралт": 0, "Хяналт": 0}
    total = 0

    for r in source.aggregate(pipeline):
        puu_id = r["_id"]
        group  = GROUP_LABEL.get(puu_id, "Хяналт")
        count  = r["count"]
        by_scale.append({
            "puuId":     puu_id,
            "puuName":   r.get("puuName") or f"Пүү {puu_id}",
            "group":     group,
            "count":     count,
            "avgWeight": round(r.get("avgWeight") or 0),
        })
        group_totals[group] = group_totals.get(group, 0) + count
        total += count

    return {
        "range":       range_key,
        "byScale":     by_scale,
        "groupTotals": group_totals,
        "total":       total,
        "from":        from_dt,
        "computedAt":  datetime.now(timezone.utc),
    }


def refresh():
    client = MongoClient(MONGO_URI)
    try:
        db     = client[DB_NAME]
        source = db["DashboardData"]
        stats  = db["DashboardStats"]
        for range_key in RANGES:
            result = _compute(source, range_key)
            stats.update_one(
                {"range": range_key},
                {"$set": result},
                upsert=True,
            )
            logger.warning("[Dashboard] %s → total=%d computedAt=%s",
                           range_key, result["total"],
                           result["computedAt"].strftime("%H:%M:%S"))
    finally:
        client.close()


def start_refresher():
    """Called by apps.py — runs refresh immediately then loops every hour."""
    logger.warning("[Dashboard] Background refresher starting...")
    try:
        refresh()
    except Exception as e:
        logger.warning("[Dashboard] Initial refresh error: %s", e)
    while True:
        time.sleep(INTERVAL)
        try:
            refresh()
        except Exception as e:
            logger.warning("[Dashboard] Refresh error: %s", e)


class Command(BaseCommand):
    help = "Aggregate dashboard stats hourly and store in DashboardStats collection"

    def add_arguments(self, parser):
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Run continuously every hour (default: run once and exit)",
        )

    def handle(self, *args, **options):
        logger.warning("[Dashboard] Starting...")
        refresh()

        if options["loop"]:
            logger.warning("[Dashboard] Loop mode — running every %ds", INTERVAL)
            while True:
                time.sleep(INTERVAL)
                refresh()
