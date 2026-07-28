from django.utils import timezone
from .models import Alert, AppSetting, Inventory

def app_context(request):
    data={'app_settings':AppSetting.get_solo()}
    if request.user.is_authenticated and getattr(getattr(request.user,'profile',None),'role',None)=='ADMIN':
        today=timezone.localdate(); settings=AppSetting.get_solo(); now=timezone.localtime()
        done=Inventory.objects.filter(inventory_date=today,inventory_type=Inventory.DAILY,state__in=[Inventory.FINAL,Inventory.FINAL_ALERT]).exists()
        data['missing_daily_now']=not done and now.time()>=settings.daily_deadline
        data['open_alert_count']=Alert.objects.filter(resolved=False).count()
    return data
