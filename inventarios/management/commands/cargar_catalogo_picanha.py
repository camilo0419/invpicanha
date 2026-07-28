import re
import unicodedata
import hashlib
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from inventarios.models import Product
from inventarios.catalogo_fuente import DIARIO as FUENTE_DIARIA
from inventarios.catalogo_fuente import GENERAL as FUENTE_GENERAL


CATEGORY_PREFIX = {
    "ABARROTES": "ABA",
    "FRUVER": "FRU",
    "LACTEOS": "LAC",
    "OTROS": "OTR",
    "PRODUCCIONES": "PRD",
    "PROTEINA": "PRO",
    "CERVEZA": "CER",
    "LIMONADAS": "LIM",
    "MODIFICADORES": "MOD",
    "SIN LICOR": "SNL",
}


def repair_source_text(value):
    return str(value).replace("�", {
        "Champi�ones Kl": "ñ",
        "Lim�n Tahiti Kl": "ó",
        "P Costilla Mixto Und (Peque�a)": "ñ",
    }.get(str(value), ""))


def stable_code(name, category):
    normalized = _plain(name)
    base = re.sub(r"[^A-Z0-9]+", "-", normalized).strip("-")
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:5].upper()
    prefix = CATEGORY_PREFIX.get(_plain(category), "OTR")
    return f"{prefix}-{base[:18].rstrip('-')}-{digest}"[:30]


def source_rows(rows):
    result = []
    for name, category, unit, value in rows:
        name = repair_source_text(name)
        category = repair_source_text(category)
        if name == "Salsa Tomate Shefrut" and value is None:
            value = "NO COMPRAN"
        result.append(
            {
                "codigo": stable_code(name, category),
                "nombre": name,
                "categoria": category,
                "unidad": unit,
                "valor": value,
            }
        )
    return result


VALID_UNITS = {
    Product.UNIT_KG,
    Product.UNIT_UND,
    Product.UNIT_LITRO,
    Product.UNIT_BOLSA,
    Product.UNIT_PORCION,
    Product.UNIT_GALON,
    Product.UNIT_OTHER,
}

LEGACY_SEED_CODES = {
    "CAR-001",
    "CAR-002",
    "LAC-001",
    "LAC-002",
    "BEB-001",
    "BEB-002",
    "BEB-003",
    "BEB-004",
    "INS-001",
    "INS-002",
    "EMP-001",
    "ASE-001",
}


def _plain(value):
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", str(value or ""))
        if not unicodedata.combining(character)
    ).strip().upper()


# Catálogo completo suministrado. La unión se calcula antes de persistir.
CATALOGO_GENERAL = source_rows(FUENTE_GENERAL)
CATALOGO_DIARIO = source_rows(FUENTE_DIARIA)


def normalize_unit(raw_unit, product_name=""):
    raw = _plain(raw_unit)
    name = _plain(product_name)
    if re.fullmatch(r"[\d.,]+", raw or ""):
        beverage_terms = ("CERVEZA", "GASEOSA", "TE ", "TÉ ", "AGUA", "JUGO", "BEBIDA")
        return Product.UNIT_UND if any(term in f"{name} " for term in beverage_terms) else Product.UNIT_OTHER
    aliases = {
        "KG": Product.UNIT_KG,
        "KG.": Product.UNIT_KG,
        "KILO": Product.UNIT_KG,
        "KILOGRAMO": Product.UNIT_KG,
        "KILOGRAMOS": Product.UNIT_KG,
        "UND": Product.UNIT_UND,
        "UNIDAD": Product.UNIT_UND,
        "UNIDADES": Product.UNIT_UND,
        "L": Product.UNIT_LITRO,
        "LT": Product.UNIT_LITRO,
        "LITRO": Product.UNIT_LITRO,
        "LITROS": Product.UNIT_LITRO,
        "BOLSA": Product.UNIT_BOLSA,
        "BOLSAS": Product.UNIT_BOLSA,
        "PORCION": Product.UNIT_PORCION,
        "PORCIONES": Product.UNIT_PORCION,
        "GALON": Product.UNIT_GALON,
        "GALONES": Product.UNIT_GALON,
    }
    if "ACEITE" in name and "GALON" in f"{name} {raw}":
        return Product.UNIT_GALON
    normalized = aliases.get(raw, Product.UNIT_OTHER)
    return normalized if normalized in VALID_UNITS else Product.UNIT_OTHER


def parse_cost(raw_value):
    if raw_value is None:
        return None, ""
    text = str(raw_value).strip()
    upper = _plain(text)
    if not text or upper in {"$ -", "$-", "-", "N/A", "NA"}:
        return None, ""
    if upper == "NO COMPRAN":
        return None, "NO COMPRAN"
    if isinstance(raw_value, Decimal):
        return raw_value, ""
    if isinstance(raw_value, (int, float)):
        return Decimal(str(raw_value)), ""
    cleaned = re.sub(r"[^\d,.\-]", "", text)
    if not cleaned or cleaned == "-":
        return None, ""
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        parts = cleaned.split(",")
        cleaned = "".join(parts) if len(parts[-1]) == 3 else ".".join(parts)
    elif cleaned.count(".") > 1 or (
        cleaned.count(".") == 1 and len(cleaned.rsplit(".", 1)[-1]) == 3
    ):
        cleaned = cleaned.replace(".", "")
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise CommandError(f"No se pudo interpretar el costo {raw_value!r}.") from exc
    return value, ""


def build_master_catalog(general_rows=None, daily_rows=None):
    general_rows = CATALOGO_GENERAL if general_rows is None else general_rows
    daily_rows = CATALOGO_DIARIO if daily_rows is None else daily_rows
    master = {}
    warnings = []

    for source, rows in (("general", general_rows), ("diario", daily_rows)):
        for position, row in enumerate(rows, 1):
            code = str(row["codigo"]).strip().upper()
            if not code:
                raise CommandError(f"Fila {position} de {source} sin código.")
            cost, cost_note = parse_cost(row.get("valor"))
            normalized = {
                "codigo": code,
                "nombre": str(row["nombre"]).strip(),
                "categoria": str(row.get("categoria") or "").strip(),
                "unidad_medida": normalize_unit(row.get("unidad"), row["nombre"]),
                "valor_unitario_promedio": cost,
                "observacion_costo": cost_note,
                "incluir_inventario_general": source == "general",
                "incluir_inventario_diario": source == "diario",
            }
            if code not in master:
                master[code] = normalized
                continue
            current = master[code]
            if source == "diario":
                current["incluir_inventario_diario"] = True
                if current["valor_unitario_promedio"] != cost:
                    warnings.append(
                        f"{code} ({current['nombre']}): costo general "
                        f"{current['valor_unitario_promedio']} y diario {cost}; "
                        "se conserva el costo general."
                    )
                # General tiene prioridad para costo y observación; se conservan el
                # nombre/categoría/unidad generales para una carga reproducible.
            else:
                was_daily = current["incluir_inventario_diario"]
                current.update(normalized)
                current["incluir_inventario_diario"] = was_daily
    return master, warnings


class Command(BaseCommand):
    help = "Carga o actualiza el catálogo maestro de Picanha sin duplicar productos."

    @transaction.atomic
    def handle(self, *args, **options):
        master, warnings = build_master_catalog()
        created_count = 0
        updated_count = 0
        for order, (code, row) in enumerate(master.items(), 10):
            defaults = {
                "name": row["nombre"],
                "category": row["categoria"],
                "unidad_medida": row["unidad_medida"],
                "activo": True,
                "display_order": order,
                "permite_decimales": row["unidad_medida"]
                in {Product.UNIT_KG, Product.UNIT_LITRO, Product.UNIT_GALON},
                "incluir_inventario_diario": row["incluir_inventario_diario"],
                "incluir_inventario_general": row["incluir_inventario_general"],
                "valor_unitario_promedio": row["valor_unitario_promedio"],
                "observacion_costo": row["observacion_costo"],
            }
            # No se incluyen umbrales ni reglas de observación en defaults:
            # configuraciones administrativas existentes permanecen intactas.
            _, created = Product.objects.update_or_create(code=code, defaults=defaults)
            created_count += int(created)
            updated_count += int(not created)

        # Los códigos pertenecen al catálogo de demostración anterior. Se
        # conservan para no romper detalles históricos, pero dejan de participar
        # en inventarios nuevos ahora que existe el catálogo maestro.
        legacy_count = Product.objects.filter(code__in=LEGACY_SEED_CODES).update(
            activo=False,
            incluir_inventario_diario=False,
            incluir_inventario_general=False,
        )
        for warning in warnings:
            self.stdout.write(self.style.WARNING(f"ADVERTENCIA: {warning}"))
        self.stdout.write(
            self.style.SUCCESS(
                f"Catálogo cargado: {len(master)} productos "
                f"({created_count} creados, {updated_count} actualizados; "
                f"{legacy_count} registros de demostración desactivados)."
            )
        )
