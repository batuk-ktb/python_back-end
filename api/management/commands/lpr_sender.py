import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from django.core.management.base import BaseCommand
from lpr_sender import main


class Command(BaseCommand):
    help = 'Poll LPR logs and RFID tags every 5 s — sends to scale receiver when both are new'

    def handle(self, *args, **options):
        main()
