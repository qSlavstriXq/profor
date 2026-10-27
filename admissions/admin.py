from django.contrib import admin

from .models import AdmissionStat, Program, ProgramExam, University


class ProgramExamInline(admin.TabularInline):
    model = ProgramExam
    extra = 3


class AdmissionStatInline(admin.TabularInline):
    model = AdmissionStat
    extra = 3


@admin.register(University)
class UniversityAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "verified", "updated_at")
    list_filter = ("verified", "city")
    search_fields = ("name",)


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ("name", "university", "study_form", "verified", "updated_at")
    list_filter = ("verified", "university", "study_form")
    search_fields = ("name", "university__name")
    inlines = [ProgramExamInline, AdmissionStatInline]