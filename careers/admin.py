from django.contrib import admin

from .models import Profession, Video


@admin.register(Profession)
class ProfessionAdmin(admin.ModelAdmin):
    list_display = ("title", "code", "verified", "updated_at")
    list_filter = ("verified",)
    search_fields = ("title", "code", "description")


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ("title", "channel", "platform", "duration", "verified", "updated_at")
    list_filter = ("verified", "platform")
    search_fields = ("title", "channel")
