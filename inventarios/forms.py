from django import forms

from .models import Alert, AppSetting, PointOfSale, Product


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "input")


class ProductForm(StyledModelForm):
    class Meta:
        model = Product
        fields = [
            "code",
            "name",
            "category",
            "unidad_medida",
            "activo",
            "display_order",
            "permite_decimales",
            "incluir_inventario_diario",
            "incluir_inventario_general",
            "valor_unitario_promedio",
            "observacion_costo",
            "critical_qty",
            "minimum_qty",
            "maximum_qty",
            "require_observation_low",
            "require_observation_high",
        ]
        widgets = {
            "critical_qty": forms.NumberInput(attrs={"min": 0, "step": "0.01"}),
            "minimum_qty": forms.NumberInput(attrs={"min": 0, "step": "0.01"}),
            "maximum_qty": forms.NumberInput(attrs={"min": 0, "step": "0.01"}),
        }


class PointOfSaleForm(StyledModelForm):
    class Meta:
        model = PointOfSale
        fields = [
            "name",
            "code",
            "active",
            "daily_deadline",
            "general_deadline",
            "general_frequency",
        ]
        widgets = {
            "daily_deadline": forms.TimeInput(attrs={"type": "time"}),
            "general_deadline": forms.TimeInput(attrs={"type": "time"}),
        }


class SettingForm(StyledModelForm):
    class Meta:
        model = AppSetting
        fields = ["require_observation_on_alert", "generate_product_alerts"]


class AlertResolveForm(StyledModelForm):
    class Meta:
        model = Alert
        fields = ["attendance_comment"]
        widgets = {
            "attendance_comment": forms.Textarea(
                attrs={"rows": 4, "required": True, "placeholder": "Describe la atención realizada"}
            )
        }

    def clean_attendance_comment(self):
        comment = self.cleaned_data["attendance_comment"].strip()
        if not comment:
            raise forms.ValidationError("El comentario de atención es obligatorio.")
        return comment


class CancellationForm(forms.Form):
    reason = forms.CharField(
        label="Motivo de anulación",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Indica el motivo"}),
    )
