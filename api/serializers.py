from rest_framework import serializers
from .models import TagReader

class TagReaderSerializer(serializers.ModelSerializer):
    class Meta:
        model = TagReader
        fields = '__all__'
