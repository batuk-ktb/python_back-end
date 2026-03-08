from djongo import models

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
    ipaddress = models.CharField(max_length=20,null=True, blank=True)
    plateImage = models.TextField(null=True, blank=True)
    def __str__(self):
        return self.container

class TagReader(models.Model):
    name = models.CharField(max_length=100)
    tag = models.CharField(max_length=100)
    date = models.DateTimeField()
    ipaddress = models.CharField(max_length=20,null=True, blank=True)

    def __str__(self):
        return f"{self.name} - {self.tag}"

class Container(models.Model):
    container_id = models.CharField(max_length=50, null=True, blank=True)
    date = models.DateTimeField(null=True, blank=True)
    control_digit = models.CharField(max_length=10, null=True, blank=True)
    readconfidence = models.FloatField(null=True, blank=True)
    plateImage = models.TextField(null=True, blank=True)

    def __str__(self):
        return str(self.container_id)
        
class Transaction(models.Model):
    puuName = models.CharField(max_length=100)
    puuId = models.IntegerField()
    Weight = models.FloatField()

    tag_id = models.CharField(max_length=100, null=True, blank=True)
    tag_date = models.DateTimeField(null=True, blank=True)

    # containers (optional)
    conR1 = models.ForeignKey(Container, null=True, blank=True, on_delete=models.SET_NULL, related_name="conR1")
    conL1 = models.ForeignKey(Container, null=True, blank=True, on_delete=models.SET_NULL, related_name="conL1")
    conR2 = models.ForeignKey(Container, null=True, blank=True, on_delete=models.SET_NULL, related_name="conR2")
    conL2 = models.ForeignKey(Container, null=True, blank=True, on_delete=models.SET_NULL, related_name="conL2")
    conR3 = models.ForeignKey(Container, null=True, blank=True, on_delete=models.SET_NULL, related_name="conR3")
    conL3 = models.ForeignKey(Container, null=True, blank=True, on_delete=models.SET_NULL, related_name="conL3")
    conR4 = models.ForeignKey(Container, null=True, blank=True, on_delete=models.SET_NULL, related_name="conR4")
    conL4 = models.ForeignKey(Container, null=True, blank=True, on_delete=models.SET_NULL, related_name="conL4")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.puuName} - {self.Weight}"