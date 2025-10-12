# app/serializers.py
from rest_framework import serializers
from bson import ObjectId
from .models import TagReader

class ObjectIdField(serializers.Field):
    def to_representation(self, value):
        return str(value)

class TagReaderSerializer(serializers.ModelSerializer):
    id = ObjectIdField(read_only=True)
    class Meta:
        model = TagReader
        fields = '__all__'
