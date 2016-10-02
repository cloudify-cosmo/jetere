from __future__ import unicode_literals

from django.db import models

# Create your models here.


class Configuration(models.Model):
    jenkins_url = models.CharField(max_length=128)
    jenkins_username = models.CharField(max_length=32)
    jenkins_password = models.CharField(max_length=32)


class Sync(models.Model):
    id = models.AutoField(primary_key=True)
    last_update = models.DateTimeField()


class Job(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=64)
    jenkins_path = models.CharField(max_length=128)

    def __str__(self):
        return 'Job [id=%d, name=%s, jenkins_path=%s]' % (self.id,
                                                          self.name,
                                                          self.jenkins_path)


class Build(models.Model):
    id = models.AutoField(primary_key=True)
    job = models.ForeignKey(Job)
    number = models.IntegerField()
    duration = models.DurationField()
    result = models.CharField(max_length=16, null=True)
    timestamp = models.DateTimeField()
    started_by = models.CharField(max_length=64, null=True)
    building = models.BooleanField(default=False)


class Test(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=128)
    status = models.CharField(max_length=16)
    class_name = models.CharField(max_length=128)
    duration = models.DurationField()
    build = models.ForeignKey(Build)

    @property
    def passed(self):
        return self.status in ('PASSED', 'FIXED')

    @property
    def failed(self):
        return self.status in ('FAILED', 'REGRESSION')

    @property
    def skipped(self):
        return self.status == 'SKIPPED'


class TestLogs(models.Model):
    id = models.AutoField(primary_key=True)
    test = models.ForeignKey(Test)
    error_stack_trace = models.TextField(null=True)
    stdout = models.TextField(null=True)
    stderr = models.TextField(null=True)
    error_details = models.TextField(null=True)
