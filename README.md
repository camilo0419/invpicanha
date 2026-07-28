# Picanha Inventarios

Aplicación Django + SQLite para el control responsive de inventarios diarios y generales de Picanha Parrilla.

## Instalación local en Windows

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_initial_data
python manage.py test
python manage.py runserver
```

Abre `http://127.0.0.1:8000/`.

## Usuarios iniciales

| Rol | Usuario | Contraseña inicial |
| --- | --- | --- |
| Punto de venta · La Central | `lacentral@picanhaparrilla.com` | `PicanhaCentral2026!` |
| Administrador funcional | `contacto@picanhaparrilla.com` | `PicanhaAdmin2026!` |

Ninguno de estos usuarios es `staff` ni `superuser`. Cambia las contraseñas antes de un uso real:

```powershell
python manage.py changepassword lacentral@picanhaparrilla.com
python manage.py changepassword contacto@picanhaparrilla.com
```

## Datos iniciales

El comando `seed_initial_data` es idempotente: crea o actualiza el punto `CENTRAL`, los dos usuarios funcionales, su perfil y un catálogo de ejemplo sin duplicar registros.

## Funcionalidad

- Roles funcionales con permisos verificados en backend.
- Inventarios diarios y generales con snapshots históricos de producto y reglas.
- Guardado de borradores, validación, finalización transaccional y bloqueo.
- Clasificación centralizada: crítico, bajo, normal, alto, sin regla y no contado.
- Reapertura y anulación administrativas sin eliminar históricos.
- Alertas internas por producto, atención con comentario y trazabilidad.
- CRUD de productos, configuración operativa y bitácora de auditoría.
- Protección CSRF, acciones sensibles por POST e IDOR restringido por punto de venta.
- Interfaz responsive para teléfono, tableta y computador.

## Configuración para producción

El proyecto queda preparado para pruebas locales, no para exposición directa a Internet. Antes de desplegar:

- define una `DJANGO_SECRET_KEY` larga y aleatoria;
- usa `DJANGO_DEBUG=0`;
- configura `DJANGO_ALLOWED_HOSTS`;
- habilita HTTPS, cookies seguras, redirección SSL y HSTS;
- sirve la aplicación con un servidor WSGI/ASGI;
- establece copias de seguridad de `db.sqlite3`;
- considera PostgreSQL si aumenta la concurrencia de escritura.
