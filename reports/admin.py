from django.contrib import admin

from . import models

# Register your models here.


@admin.register(models.Configuration)
class ConfigurationAdmin(admin.ModelAdmin):
    pass


@admin.register(models.Job)
class JobAdmin(admin.ModelAdmin):
    pass
