from django.db import models

# Create your models here.

class CameraData(models.Model):
    container = models.CharField(max_length=50)
    date = models.DateTimeField()
    ocrtime = models.CharField(max_length=10)
    digitheight = models.CharField(max_length=10)
    left = models.IntegerField()
    top = models.IntegerField()
    right = models.IntegerField()
    bottom = models.IntegerField()
    confidencecode = models.CharField(max_length=5)
    controldigit = models.CharField(max_length=5)
    numdigits = models.CharField(max_length=5)
    ownercity = models.CharField(max_length=100)
    ownercode = models.CharField(max_length=20)
    ownercompany = models.CharField(max_length=100)
    readconfidence = models.CharField(max_length=10)
    serialcode = models.CharField(max_length=50)
    sizetypecode = models.CharField(max_length=10, blank=True)

    def __str__(self):
        return self.container
