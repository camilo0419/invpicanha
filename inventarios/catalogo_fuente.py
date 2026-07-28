"""Fuente suministrada para el catálogo maestro de Picanha Parrilla."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from inventarios.models import Product


GENERAL = [
    # nombre, categoría, unidad, valor promedio
    ("Aceite en Galon", "Abarrotes", "GALON", "120500.00"),
    ("Aceite Vegetal", "Abarrotes", "LITRO", "6260.00"),
    ("Arepa Peq Und", "Abarrotes", "UND", None),
    ("Arroz Blanco Kl", "Abarrotes", "KG", "3728.00"),
    ("Arroz de Coco Diana Kl", "Abarrotes", "KG", None),
    ("Azucar Blanca Kl", "Abarrotes", "KG", "4000.00"),
    ("Crema Marinera", "Abarrotes", "KG", "56250.00"),
    ("Curry Kl", "Abarrotes", "KG", None),
    ("Demiglace", "Abarrotes", "KG", "78700.00"),
    ("Frijol Kl", "Abarrotes", "KG", "17500.00"),
    ("Huevo Und", "Abarrotes", "UND", "359.67"),
    ("Maggie Kl", "Abarrotes", "KG", "24200.00"),
    ("Maicitos Kl", "Abarrotes", "KG", "8500.00"),
    ("Panela Kl", "Abarrotes", "KG", "7250.00"),
    ("Pasta de Tomate Kl", "Abarrotes", "KG", "15000.00"),
    ("Pasta Penne Kl", "Abarrotes", "KG", "8000.00"),
    ("Salsa Tomate Shefrut", "Abarrotes", "KG", None),
    ("Vino Blanco", "Abarrotes", "LITRO", "27000.00"),

    ("Aguacate Kl", "Fruver", "KG", "11000.00"),
    ("Ajo Kl", "Fruver", "KG", "11000.00"),
    ("Albahaca", "Fruver", "KG", None),
    ("Cebolla Blanca Kl", "Fruver", "KG", "2500.00"),
    ("Cebolla Morada Kl", "Fruver", "KG", "4500.00"),
    ("Cebolla Puerro", "Fruver", "KG", "8500.00"),
    ("Champiñones Kl", "Fruver", "KG", "30000.00"),
    ("Lechuga Crespa Kl", "Fruver", "KG", "2500.00"),
    ("Limón Tahiti Kl", "Fruver", "KG", "2500.00"),
    ("Papa Nevada Kl", "Fruver", "KG", "5500.00"),
    ("Platano Kl", "Fruver", "KG", "4000.00"),
    ("Tomate Chonto Kl", "Fruver", "KG", "5500.00"),
    ("Zanahoria Kl", "Fruver", "KG", "3000.00"),

    ("Crema de Leche", "Lacteos", "LITRO", "14940.46"),
    ("Leche", "Lacteos", "BOLSA", "2990.00"),
    ("Queso Mozzarella Kl", "Lacteos", "KG", None),
    ("Queso Parmesano Kl", "Lacteos", "KG", "34800.00"),

    ("Pan Baguette Und", "Otros", "UND", "2000.00"),
    ("Ripio de Papa Kl", "Otros", "KG", "8000.00"),

    ("P Base 3 Quesos Kl", "Producciones", "KG", "31000.00"),
    ("P Base Bolognesa Kl", "Producciones", "KG", "19000.00"),
    ("P Chimichurri Kl", "Producciones", "KG", "17200.00"),
    ("P Costilla Mixto Und (Pequeña)", "Producciones", "UND", None),
    ("P Costilla Porcion Und", "Producciones", "UND", None),
    ("P Pasta de Ajo Kl", "Producciones", "KG", None),
    ("P Pasta de Albahaca Kl", "Producciones", "KG", "39500.00"),
    ("P Patacones Und", "Producciones", "UND", None),
    ("P Salsa BBQ Kl", "Producciones", "KG", "15500.00"),
    ("P Salsal Pomodoro Kl", "Producciones", "KG", "9200.00"),
    ("P Vinagreta de la Casa Kl", "Producciones", "KG", "11700.00"),

    ("Camaron Kl", "Proteina", "KG", "34000.00"),
    ("Cerdo 120 gr", "Proteina", "UND", "2148.00"),
    ("Chicharron Cazuela Kl", "Proteina", "PORCION", "2955.00"),
    ("Chicharron Und", "Proteina", "UND", "4418.75"),
    ("Chorizo Und", "Proteina", "UND", "1250.00"),
    ("Churrasco 300 gr. Und", "Proteina", "UND", "14900.00"),
    ("Chuzo de Pollo Und", "Proteina", "UND", "6325.00"),
    ("Costilla Cerdo Kl", "Proteina", "KG", "21000.00"),
    ("Filete de Tilapia Und", "Proteina", "UND", "5500.00"),
    ("Lomito de Cerdo Und", "Proteina", "UND", "6766.93"),
    ("Pechuga 120 gr Und", "Proteina", "UND", "2783.00"),
    ("Pechuga 250 gr. Und", "Proteina", "UND", "6325.00"),
    ("Punta de Anca Und", "Proteina", "UND", "17000.00"),
    ("Recorte de Pechuga Kl", "Proteina", "UND", "25300.00"),
    ("Res 120 gr. Und", "Proteina", "UND", "4000.00"),
    ("Salmon Und", "Proteina", "UND", "15000.00"),
    ("Solomo Und", "Proteina", "UND", "14700.00"),
    ("Tilapia 500 gr. Und", "Proteina", "UND", "9500.00"),
    ("Tocineta kl", "Proteina", "KG", "18000.00"),
    ("Tocino Horneado Porcion Und", "Proteina", "PORCION", "9500.00"),
    ("Trucha 300 gr. Und", "Proteina", "UND", "7500.00"),

    ("CLUB COLOMBIA", "CERVEZA", "UND", None),
    ("HEINEKEN", "CERVEZA", "UND", None),
    ("PILSEN", "CERVEZA", "UND", None),

    ("LIMONADA CEREZADA", "LIMONADAS", "UND", "2612.50"),
    ("LIMONADA DE COCO", "LIMONADAS", "UND", "2565.00"),
    ("LIMONADA NATURAL", "LIMONADAS", "UND", None),

    ("AGUA LIMON", "Modificadores", "UND", "2083.33"),
    ("AGUA MARACUYA", "Modificadores", "UND", "2083.33"),
    ("COCA-COLA", "Modificadores", "UND", "2088.75"),
    ("JUGO FRESA", "Modificadores", "UND", "1520.00"),
    ("JUGO GUANABANA", "Modificadores", "UND", "1710.00"),
    ("JUGO MANDARINA", "Modificadores", "UND", "1900.00"),
    ("JUGO MANGO", "Modificadores", "UND", "1520.00"),
    ("JUGO MARACUYA", "Modificadores", "UND", "2280.00"),
    ("JUGO MORA", "Modificadores", "UND", "1520.00"),
    ("PREMIO ROJO", "Modificadores", "UND", "2091.67"),
    ("QUATRO", "Modificadores", "UND", "2091.67"),
    ("SPRITE", "Modificadores", "UND", "2091.67"),
    ("TEA DURAZNO", "Modificadores", "UND", None),
    ("TEA LIMON", "Modificadores", "UND", None),

    ("AGUA MANANTIAL CON GAS", "SIN LICOR", "UND", "2400.00"),
    ("AGUA MANANTIAL SIN GAS", "SIN LICOR", "UND", "2400.00"),
    ("GASEOSA LITRO 1/4", "SIN LICOR", "UND", None),
]


DIARIO = [
    # nombre, categoría, unidad, valor diario informado
    ("Pasta de Tomate Kl", "Abarrotes", "KG", None),
    ("Pasta Penne Kl", "Abarrotes", "KG", None),
    ("Salsa Tomate Shefrut", "Abarrotes", "KG", None),

    ("CLUB COLOMBIA", "CERVEZA", "UND", None),
    ("HEINEKEN", "CERVEZA", "UND", None),
    ("PILSEN", "CERVEZA", "UND", None),

    ("Crema de Leche", "Lacteos", "KG", "14940.46"),
    ("Leche", "Lacteos", "KG", "2990.00"),
    ("Queso Mozzarella Kl", "Lacteos", "KG", None),
    ("Queso Parmesano Kl", "Lacteos", "KG", None),

    ("PREMIO ROJO", "Modificadores", "UND", "2091.67"),
    ("QUATRO", "Modificadores", "UND", "2091.67"),
    ("SPRITE", "Modificadores", "UND", "2091.67"),
    ("TEA DURAZNO", "Modificadores", "UND", None),
    ("TEA LIMON", "Modificadores", "UND", None),

    ("Pan Baguette Und", "Otros", "UND", None),

    ("P Base 3 Quesos Kl", "Producciones", "KG", None),
    ("P Base Bolognesa Kl", "Producciones", "KG", None),
    ("P Chimichurri Kl", "Producciones", "KG", None),
    ("P Costilla Mixto Und (Pequeña)", "Producciones", "UND", None),
    ("P Costilla Porcion Und", "Producciones", "UND", None),
    ("P Pasta de Ajo Kl", "Producciones", "KG", None),
    ("P Pasta de Albahaca Kl", "Producciones", "KG", None),
    ("P Patacones Und", "Producciones", "UND", None),
    ("P Salsa BBQ Kl", "Producciones", "KG", None),
    ("P Salsal Pomodoro Kl", "Producciones", "KG", None),
    ("P Vinagreta de la Casa Kl", "Producciones", "KG", None),

    ("Camaron Kl", "Proteina", "KG", "34.00"),
    ("Cerdo 120 gr", "Proteina", "UND", "2177.83"),
    ("Chicharron Cazuela Kl", "Proteina", "KG", "2070.00"),
    ("Chicharron Und", "Proteina", "UND", "4418.75"),
    ("Chorizo Und", "Proteina", "UND", "1250.00"),
    ("Churrasco 300 gr. Und", "Proteina", "UND", "14827.40"),
    ("Chuzo de Pollo Und", "Proteina", "UND", "6325.00"),
    ("Costilla Cerdo Kl", "Proteina", "KG", "21.00"),
    ("Filete de Tilapia Und", "Proteina", "UND", "542.86"),
    ("Lomito de Cerdo Und", "Proteina", "UND", "6766.93"),
    ("Pechuga 120 gr Und", "Proteina", "UND", "2783.00"),
    ("Pechuga 250 gr. Und", "Proteina", "UND", "6325.00"),
    ("Punta de Anca Und", "Proteina", "UND", "27118.00"),
    ("Recorte de Pechuga Kl", "Proteina", "KG", "25300.00"),
    ("Res 120 gr. Und", "Proteina", "UND", "3965.58"),
    ("Salmon Und", "Proteina", "UND", "16343.00"),
    ("Solomo Und", "Proteina", "UND", "14700.00"),
    ("Tilapia 500 gr. Und", "Proteina", "UND", "14269.00"),
    ("Tocineta kl", "Proteina", "KG", None),
    ("Tocino Horneado Porcion Und", "Proteina", "UND", None),
    ("Trucha 300 gr. Und", "Proteina", "UND", "14840.00"),

    ("AGUA MANANTIAL CON GAS", "SIN LICOR", "UND", "2400.00"),
    ("AGUA MANANTIAL SIN GAS", "SIN LICOR", "UND", "2400.00"),
    ("GASEOSA LITRO 1/4", "SIN LICOR", "UND", None),
    ("AGUA SABOR", "SIN LICOR", "UND", None),
    ("COCOCAOLA", "SIN LICOR", "UND", None),
    ("SODA", "SIN LICOR", "UND", None),
    ("TEA MANGO", "SIN LICOR", "UND", None),
    ("DEL VALLE", "SIN LICOR", "UND", None),

    ("PAPA A LA FRANCESA", "Otros", "UND", None),
    ("P SALSA BLANCA", "Producciones", "KG", None),
]


CATEGORY_PREFIX = {
    "Abarrotes": "ABA",
    "Fruver": "FRU",
    "Lacteos": "LAC",
    "Otros": "OTR",
    "Producciones": "PRD",
    "Proteina": "PRO",
    "CERVEZA": "CER",
    "LIMONADAS": "LIM",
    "Modificadores": "MOD",
    "SIN LICOR": "SNL",
}


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"\s+", " ", value).strip()
    return value


def stable_code(name: str, category: str) -> str:
    normalized = normalize_text(name).upper()
    base = re.sub(r"[^A-Z0-9]+", "-", normalized).strip("-")
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:5].upper()
    prefix = CATEGORY_PREFIX.get(category, "OTR")
    short = base[:18].rstrip("-")
    return f"{prefix}-{short}-{digest}"[:30]


def decimal_or_none(value):
    if value in (None, "", "-", "$ -"):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise CommandError(f"Valor monetario inválido: {value!r}") from exc


def first_existing_field(*names: str) -> str | None:
    field_names = {field.name for field in Product._meta.get_fields()}
    return next((name for name in names if name in field_names), None)


class Command(BaseCommand):
    help = "Carga o actualiza el catálogo maestro de productos de Picanha Parrilla."

    def add_arguments(self, parser):
        parser.add_argument(
            "--desactivar-ausentes",
            action="store_true",
            help=(
                "Desactiva productos existentes que no estén en este catálogo. "
                "No se recomienda usarlo en la primera ejecución."
            ),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        fields = {field.name for field in Product._meta.get_fields()}

        required = {
            "name",
            "code",
            "category",
            "unidad_medida",
            "activo",
            "incluir_inventario_diario",
            "incluir_inventario_general",
            "permite_decimales",
            "display_order",
        }
        missing = sorted(required - fields)
        if missing:
            raise CommandError(
                "El modelo Product no tiene los campos requeridos: "
                + ", ".join(missing)
            )

        cost_field = first_existing_field(
            "valor_unitario_promedio",
        )
        cost_note_field = first_existing_field(
            "observacion_costo",
        )

        general_by_name = {normalize_text(row[0]): row for row in GENERAL}
        daily_by_name = {normalize_text(row[0]): row for row in DIARIO}
        all_names = list(dict.fromkeys([*general_by_name, *daily_by_name]))

        created = 0
        updated = 0
        unchanged = 0
        warnings = []
        processed_codes = set()

        for order, normalized_name in enumerate(all_names, start=10):
            general = general_by_name.get(normalized_name)
            daily = daily_by_name.get(normalized_name)

            source = general or daily
            assert source is not None
            name, category, unit, _ = source

            general_cost = decimal_or_none(general[3]) if general else None
            daily_cost = decimal_or_none(daily[3]) if daily else None

            # Prioridad: valor general; si no existe, valor diario.
            selected_cost = general_cost if general_cost is not None else daily_cost

            if (
                general_cost is not None
                and daily_cost is not None
                and general_cost != daily_cost
            ):
                warnings.append(
                    f"{name}: general={general_cost} / diario={daily_cost}. "
                    "Se conservó el valor general."
                )

            # Para productos compartidos se conserva categoría/unidad general.
            if general:
                category = general[1]
                unit = general[2]
            else:
                category = daily[1]
                unit = daily[2]

            code = stable_code(name, category)
            processed_codes.add(code)

            defaults = {
                "name": name.strip(),
                "category": category.strip(),
                "unidad_medida": unit.strip(),
                "activo": True,
                "incluir_inventario_diario": daily is not None,
                "incluir_inventario_general": general is not None,
                "permite_decimales": unit in {"KG", "LITRO", "GALON"},
                "display_order": order,
            }

            if cost_field:
                defaults[cost_field] = selected_cost

            if cost_note_field and name == "Salsa Tomate Shefrut":
                defaults[cost_note_field] = "NO COMPRAN"

            product, was_created = Product.objects.get_or_create(
                code=code,
                defaults=defaults,
            )

            if was_created:
                created += 1
                continue

            changed_fields = []
            for field_name, new_value in defaults.items():
                old_value = getattr(product, field_name)
                if old_value != new_value:
                    setattr(product, field_name, new_value)
                    changed_fields.append(field_name)

            # No se modifican deliberadamente:
            # critical_qty, minimum_qty, maximum_qty,
            # ni reglas de observación configuradas por el administrador.

            if changed_fields:
                product.save(update_fields=[*changed_fields, "updated_at"])
                updated += 1
            else:
                unchanged += 1

        deactivated = 0
        if options["desactivar_ausentes"]:
            qs = Product.objects.exclude(code__in=processed_codes).filter(activo=True)
            deactivated = qs.update(activo=False)

        self.stdout.write(self.style.SUCCESS("Catálogo procesado correctamente."))
        self.stdout.write(f"Productos creados: {created}")
        self.stdout.write(f"Productos actualizados: {updated}")
        self.stdout.write(f"Productos sin cambios: {unchanged}")
        self.stdout.write(f"Productos desactivados: {deactivated}")
        self.stdout.write(f"Total catálogo: {len(all_names)}")

        if not cost_field:
            self.stdout.write(
                self.style.WARNING(
                    "El modelo Product no tiene un campo reconocido para el valor "
                    "unitario promedio. Se cargaron productos, categorías, unidades "
                    "y pertenencia a inventario, pero no los costos."
                )
            )
            self.stdout.write(
                "El campo requerido es valor_unitario_promedio."
            )

        if warnings:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "Diferencias entre valores de inventario general y diario:"
                )
            )
            for warning in warnings:
                self.stdout.write(f"- {warning}")

        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "Revisar manualmente posibles nombres distintos: "
                "'COCA-COLA' y 'COCOCAOLA'. Se cargaron como productos separados."
            )
        )
