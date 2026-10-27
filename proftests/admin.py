from django.contrib import admin

from .models import (
    Answer, Attempt, Interpretation, Option, Participant, Question, Scale, StrategyReport, Test,
)


class ScaleInline(admin.TabularInline):
    model = Scale
    extra = 0


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    show_change_link = True


@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ("title", "code", "is_active", "updated_at")
    inlines = [ScaleInline, QuestionInline]


class InterpretationInline(admin.TabularInline):
    model = Interpretation
    extra = 0


@admin.register(Scale)
class ScaleAdmin(admin.ModelAdmin):
    list_display = ("name", "test", "code")
    list_filter = ("test",)
    inlines = [InterpretationInline]


class OptionInline(admin.TabularInline):
    model = Option
    extra = 0


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "test")
    list_filter = ("test",)
    inlines = [OptionInline]


class AttemptInline(admin.TabularInline):
    model = Attempt
    extra = 0
    fields = ("test", "started_at", "finished_at", "scores")
    readonly_fields = fields


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ("code", "created_at")
    search_fields = ("code",)
    inlines = [AttemptInline]


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    readonly_fields = ("question", "option")


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ("participant", "test", "started_at", "finished_at")
    list_filter = ("test",)
    search_fields = ("participant__code",)
    inlines = [AnswerInline]


@admin.register(StrategyReport)
class StrategyReportAdmin(admin.ModelAdmin):
    list_display = ("participant", "model_name", "created_at")
    search_fields = ("participant__code",)
    readonly_fields = ("participant", "model_name", "basis", "content", "created_at")
