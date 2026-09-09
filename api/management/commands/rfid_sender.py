import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from django.core.management.base import BaseCommand
from rfid_sender import main


class Command(BaseCommand):
    help = 'Poll RFID tags every 5 s — sends to scale receiver when a new tag date is seen'

    def handle(self, *args, **options):
        main()
