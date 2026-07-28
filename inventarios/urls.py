from django.urls import path
from . import views
urlpatterns=[
path('login/',views.login_view,name='login'),path('logout/',views.logout_view,name='logout'),path('',views.dashboard,name='dashboard'),
path('inventario/iniciar/<str:kind>/',views.inventory_start,name='inventory_start'),path('inventario/<int:pk>/captura/',views.inventory_fill,name='inventory_fill'),path('inventario/<int:pk>/',views.inventory_detail,name='inventory_detail'),path('inventarios/',views.inventory_list,name='inventory_list'),
path('productos/',views.products,name='products'),path('productos/nuevo/',views.product_form,name='product_create'),path('productos/<int:pk>/editar/',views.product_form,name='product_edit'),
path('alertas/',views.alerts,name='alerts'),path('alertas/<int:pk>/atender/',views.alert_resolve,name='alert_resolve'),path('configuracion/',views.settings_view,name='settings')]
