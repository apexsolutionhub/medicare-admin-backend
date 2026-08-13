from django.contrib import admin

from .models import ApexMember


@admin.register(ApexMember)
class ApexMemberAdmin(admin.ModelAdmin):
    list_display = ("username", "full_name", "email", "is_active", "is_superadmin", "created_at")
    list_filter = ("is_active", "is_superadmin")
    search_fields = ("username", "full_name", "email")
