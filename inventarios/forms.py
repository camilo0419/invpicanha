from django import forms
from .models import Product, AppSetting, Alert
class ProductForm(forms.ModelForm):
    class Meta:
        model=Product; fields=['code','name','category','unit','active','include_daily','include_general','allows_decimals','critical_qty','minimum_qty','maximum_qty','display_order']
        widgets={k:forms.TextInput(attrs={'class':'input'}) for k in ['code','name','category','unit']}
    def clean(self):
        d=super().clean(); c,m,x=d.get('critical_qty'),d.get('minimum_qty'),d.get('maximum_qty')
        if c is not None and m is not None and c>m: self.add_error('critical_qty','Debe ser menor o igual al mínimo.')
        if m is not None and x is not None and m>x: self.add_error('maximum_qty','Debe ser mayor o igual al mínimo.')
        return d
class SettingForm(forms.ModelForm):
    class Meta:
        model=AppSetting; fields=['daily_deadline','general_frequency_days','general_deadline','require_observation_on_alert']; widgets={'daily_deadline':forms.TimeInput(attrs={'type':'time'}),'general_deadline':forms.TimeInput(attrs={'type':'time'})}
class AlertResolveForm(forms.ModelForm):
    class Meta: model=Alert; fields=['resolution_note']; widgets={'resolution_note':forms.Textarea(attrs={'rows':3})}
