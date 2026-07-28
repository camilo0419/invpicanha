# Inventarios Picanha Parrilla

Aplicación Django + SQLite responsive para inventario diario y general, historial auditable, criterios administrables y alertas web.

## Inicio rápido en Windows

1. Instala Python 3.12 o 3.13 y marca **Add Python to PATH**.
2. Descomprime el proyecto.
3. Haz doble clic en `setup_windows.bat`.
4. Abre `http://127.0.0.1:8000/`.

Después de la primera instalación usa `run_windows.bat`.

## Usuarios iniciales

- Punto de venta: `lacentral@picanhaparrilla.com` / `PicanhaCentral2026!`
- Administrador: `contacto@picanhaparrilla.com` / `PicanhaAdmin2026!`

Cambia las contraseñas antes de producción con:

```bash
python manage.py changepassword lacentral@picanhaparrilla.com
python manage.py changepassword contacto@picanhaparrilla.com
```

## Funcionalidad incluida

- Roles propios: administrador y punto de venta. Ninguno es superusuario.
- Dos botones: inventario diario e inventario general.
- Guardado en borrador y finalización con bloqueo lógico.
- Un inventario por tipo, fecha y punto.
- Productos configurables para diario/general.
- Umbrales crítico, mínimo y máximo administrables.
- Observación obligatoria en productos con alerta (configurable).
- Alertas web y bandeja de atención para administrador.
- Historial desplazable, filtros y detalle producto por producto.
- Diseño responsive para móvil y escritorio.
- SQLite sin servicios externos.

## Nota para producción

Para publicar en internet cambia `DJANGO_SECRET_KEY`, desactiva `DJANGO_DEBUG`, configura `DJANGO_ALLOWED_HOSTS`, usa HTTPS y un servidor WSGI. SQLite es apropiado para este uso pequeño con baja concurrencia; realiza copias de seguridad periódicas de `db.sqlite3`.
