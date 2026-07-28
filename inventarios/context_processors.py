from .models import Alert, AppSetting, Profile


def app_context(request):
    data = {"app_settings": AppSetting.get_solo()}
    profile = getattr(request.user, "profile", None) if request.user.is_authenticated else None
    data["functional_profile"] = profile
    if profile and profile.active and profile.role == Profile.ADMIN:
        data["open_alert_count"] = Alert.objects.filter(attended=False).count()
    return data
