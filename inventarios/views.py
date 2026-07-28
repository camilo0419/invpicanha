from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .decorators import role_required
from .models import Profile, Product, Inventory, InventoryItem, Alert, AppSetting
from .forms import ProductForm, SettingForm, AlertResolveForm
from .services import create_inventory, finalize_inventory

def login_view(request):
    if request.user.is_authenticated: return redirect('dashboard')
    form=AuthenticationForm(request,data=request.POST or None)
    if request.method=='POST' and form.is_valid(): login(request,form.get_user()); return redirect('dashboard')
    return render(request,'registration/login.html',{'form':form})
@login_required
def logout_view(request):
    if request.method=='POST': logout(request)
    return redirect('login')
@login_required
def dashboard(request):
    role=request.user.profile.role
    if role==Profile.ADMIN:
        recent=Inventory.objects.select_related('created_by')[:10]; alerts=Alert.objects.filter(resolved=False)[:8]
        today=timezone.localdate(); today_inv=Inventory.objects.filter(inventory_date=today)
        return render(request,'inventarios/admin_dashboard.html',{'recent':recent,'alerts':alerts,'today_inv':today_inv})
    recent=Inventory.objects.filter(created_by=request.user)[:8]
    return render(request,'inventarios/pos_dashboard.html',{'recent':recent})
@role_required(Profile.POS,Profile.ADMIN)
def inventory_start(request,kind):
    inv_type=Inventory.DAILY if kind=='diario' else Inventory.GENERAL
    inv,created=create_inventory(request.user,inv_type)
    messages.info(request,'Inventario creado.' if created else 'Ya existe un inventario de este tipo para hoy; se abrió el existente.')
    return redirect('inventory_fill',pk=inv.pk)
@role_required(Profile.POS,Profile.ADMIN)
def inventory_fill(request,pk):
    inv=get_object_or_404(Inventory,pk=pk)
    if request.user.profile.role==Profile.POS and inv.created_by_id!=request.user.id: return redirect('dashboard')
    if inv.is_final: return redirect('inventory_detail',pk=inv.pk)
    items=list(inv.items.select_related('product'))
    if request.method=='POST':
        action=request.POST.get('action','save'); errors=[]
        with transaction.atomic():
            for item in items:
                raw=request.POST.get(f'qty_{item.id}','').strip().replace(',','.')
                obs=request.POST.get(f'obs_{item.id}','').strip()
                try: qty=None if raw=='' else Decimal(raw)
                except InvalidOperation: errors.append(f'Cantidad inválida en {item.product_name}.'); continue
                if qty is not None and qty<0: errors.append(f'La cantidad de {item.product_name} no puede ser negativa.'); continue
                if qty is not None and not item.product.allows_decimals and qty != qty.to_integral_value(): errors.append(f'{item.product_name} solo admite enteros.'); continue
                item.quantity=qty; item.observation=obs; item.result=item.product.classify(qty); item.save()
            inv.general_observation=request.POST.get('general_observation','').strip(); inv.total_counted=inv.items.exclude(quantity__isnull=True).count(); inv.save(update_fields=['general_observation','total_counted'])
        if errors:
            for e in errors: messages.error(request,e)
        elif action=='finalize':
            try: finalize_inventory(inv); messages.success(request,'Inventario finalizado correctamente.'); return redirect('inventory_detail',pk=inv.pk)
            except ValueError as e: messages.error(request,str(e))
        else: messages.success(request,'Borrador guardado.'); return redirect('inventory_fill',pk=inv.pk)
    return render(request,'inventarios/inventory_fill.html',{'inv':inv,'items':items})
@login_required
def inventory_list(request):
    qs=Inventory.objects.select_related('created_by')
    if request.user.profile.role==Profile.POS: qs=qs.filter(created_by=request.user)
    if request.GET.get('type'): qs=qs.filter(inventory_type=request.GET['type'])
    if request.GET.get('state'): qs=qs.filter(state=request.GET['state'])
    if request.GET.get('q'): qs=qs.filter(Q(point_name__icontains=request.GET['q'])|Q(created_by__username__icontains=request.GET['q']))
    page=Paginator(qs,20).get_page(request.GET.get('page'))
    return render(request,'inventarios/inventory_list.html',{'page':page})
@login_required
def inventory_detail(request,pk):
    inv=get_object_or_404(Inventory.objects.select_related('created_by'),pk=pk)
    if request.user.profile.role==Profile.POS and inv.created_by_id!=request.user.id: return redirect('dashboard')
    filt=request.GET.get('result'); items=inv.items.all(); items=items.filter(result=filt) if filt else items
    return render(request,'inventarios/inventory_detail.html',{'inv':inv,'items':items,'filt':filt})
@role_required(Profile.ADMIN)
def products(request):
    qs=Product.objects.all(); q=request.GET.get('q','');
    if q: qs=qs.filter(Q(name__icontains=q)|Q(code__icontains=q)|Q(category__icontains=q))
    return render(request,'inventarios/products.html',{'products':qs,'q':q})
@role_required(Profile.ADMIN)
def product_form(request,pk=None):
    obj=get_object_or_404(Product,pk=pk) if pk else None; form=ProductForm(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid(): form.save(); messages.success(request,'Producto guardado.'); return redirect('products')
    return render(request,'inventarios/product_form.html',{'form':form,'obj':obj})
@role_required(Profile.ADMIN)
def alerts(request):
    qs=Alert.objects.select_related('inventory');
    if request.GET.get('status')=='open': qs=qs.filter(resolved=False)
    if request.GET.get('status')=='resolved': qs=qs.filter(resolved=True)
    return render(request,'inventarios/alerts.html',{'alerts':qs})
@role_required(Profile.ADMIN)
def alert_resolve(request,pk):
    alert=get_object_or_404(Alert,pk=pk); form=AlertResolveForm(request.POST or None,instance=alert)
    if request.method=='POST' and form.is_valid():
        alert=form.save(commit=False); alert.resolved=True; alert.resolved_by=request.user; alert.resolved_at=timezone.now(); alert.save(); messages.success(request,'Alerta marcada como atendida.'); return redirect('alerts')
    return render(request,'inventarios/alert_resolve.html',{'alert':alert,'form':form})
@role_required(Profile.ADMIN)
def settings_view(request):
    obj=AppSetting.get_solo(); form=SettingForm(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid(): form.save(); messages.success(request,'Configuración guardada.'); return redirect('settings')
    return render(request,'inventarios/settings.html',{'form':form})
