from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from inventarios.models import Profile, Product, AppSetting
class Command(BaseCommand):
    help='Crea usuarios y catálogo inicial para pruebas.'
    def handle(self,*args,**kwargs):
        U=get_user_model()
        for username,password,role in [('lacentral@picanhaparrilla.com','PicanhaCentral2026!',Profile.POS),('contacto@picanhaparrilla.com','PicanhaAdmin2026!',Profile.ADMIN)]:
            u,created=U.objects.get_or_create(username=username,defaults={'email':username,'is_staff':False,'is_superuser':False})
            if created: u.set_password(password); u.save()
            Profile.objects.update_or_create(user=u,defaults={'role':role,'point_name':'La Central','active':True})
        AppSetting.get_solo()
        rows=[
        ('CAR-001','Picanha','Carnes','Kg',True,5,12,45),('CAR-002','Punta de anca','Carnes','Kg',True,4,10,35),('LAC-001','Leche','Lácteos','Litro',True,2,6,30),('LAC-002','Queso parmesano','Lácteos','Kg',True,1,3,12),('BEB-001','Pilsen','Cervezas','Unidad',True,6,18,100),('BEB-002','Gaseosa','Bebidas','Unidad',True,8,20,120),('INS-001','Pasta de tomate','Insumos','Kg',True,2,5,25),('EMP-001','Servilletas','Empaques','Paquete',False,2,5,30),('ASE-001','Detergente','Aseo','Litro',False,1,3,15)]
        for order,(code,name,cat,unit,daily,c,m,x) in enumerate(rows,10):
            Product.objects.update_or_create(code=code,defaults={'name':name,'category':cat,'unit':unit,'include_daily':daily,'include_general':True,'critical_qty':c,'minimum_qty':m,'maximum_qty':x,'display_order':order,'allows_decimals':unit in ['Kg','Litro']})
        self.stdout.write(self.style.SUCCESS('Datos iniciales creados.'))
        self.stdout.write('POS: lacentral@picanhaparrilla.com / PicanhaCentral2026!')
        self.stdout.write('ADMIN: contacto@picanhaparrilla.com / PicanhaAdmin2026!')
