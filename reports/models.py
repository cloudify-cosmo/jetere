from __future__ import unicode_literals

from django.db import models

# Create your models here.


class Configuration(models.Model):
    jenkins_url = models.CharField(max_length=128)
    jenkins_username = models.CharField(max_length=32)
    jenkins_password = models.CharField(max_length=32)
