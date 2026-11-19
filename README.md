# Finnegans para Claude Desktop

Extensión de Claude Desktop que conecta a Claude con Finnegans. Le pedís en
castellano, con tus palabras, lo que necesitás ("¿qué órdenes de compra
pendientes tiene este proveedor?", "pasame los clientes de Córdoba a Excel",
"cambiá la provincia de este cliente") y Claude busca el endpoint correcto, lee
los datos, los consulta, los exporta y, cuando se lo pedís, hace el cambio.

Funciona solo en Windows. Las claves de acceso las carga cada persona una única
vez, al instalar, en un formulario que Claude Desktop guarda de forma segura.

---

## Instalación

Necesitás Claude Desktop actualizado y el archivo `finnegans.mcpb` que te
pasa Juan Sbatella.

**Opción A: instalación para todo el equipo (la hace el Owner de la organización)**

1. En Claude Desktop, el Owner entra a la configuración de la organización,
   sección de extensiones.
2. Sube el archivo `finnegans.mcpb` como extensión del equipo.
3. Cada líder la activa desde Configuración, Extensiones, y completa el
   formulario (ver más abajo).

**Opción B: instalación individual**

1. Hacé doble clic en `finnegans.mcpb`, o arrastralo a la ventana de Claude
   Desktop.
2. Se abre la pantalla de instalación: tocá **Instalar** y completá el
   formulario.
3. Activá la extensión. Probá escribiendo: "verificá la conexión con
   Finnegans".

La primera vez que arranca puede tardar un poco porque prepara su propio
entorno de Python. Después abre rápido.

### El formulario, campo por campo

Cuatro claves son **personales**: cada persona carga las suyas, y con ellas
Claude entra a Finnegans con tu propio usuario. No las compartas.

- El **Client ID y el Client secret de Finnegans** te los da quien administra
  Finnegans.
- El **Client ID y la Secret key de la documentación** los encontrás vos en
  Finnegans GO → Modificar perfil → Datos personales, al final del formulario.

La **Clave del swagger** es de la empresa y ya viene cargada en la versión de
la empresa: no la cambies.

| Campo | De dónde sale | Obligatorio |
|---|---|---|
| Client ID de Finnegans | Tu identificador de la API de Finnegans. Te lo da quien administra Finnegans. | Sí |
| Client secret de Finnegans | Tu clave secreta de la API. Se guarda enmascarada. Te la da quien administra Finnegans. | Sí |
| Client ID de la documentación | Finnegans GO → Modificar perfil → Datos personales. | Sí |
| Secret key de la documentación | Finnegans GO → Modificar perfil → Datos personales. Se guarda enmascarada. | Sí |
| Clave del swagger (avanzado) | Clave de la empresa para el catálogo de endpoints. Ya viene cargada: no la cambies. Se guarda enmascarada. | Sí |
| Carpeta de exportación | Donde se guardan los Excel y CSV que pidas. Por defecto, `Documentos\Finnegans`. | No |
| URL de la API, del swagger y de la documentación (avanzado) | Direcciones de Finnegans. Ya vienen cargadas: no las cambies salvo que Juan Sbatella te lo indique. | No |

Si falta o está mal alguna clave, pedile a Claude "verificá la conexión con
Finnegans": te dice cuál es la que falla.

### Solo ves lo que tu usuario puede usar

Claude te muestra solo lo que tu usuario de Finnegans puede usar: si pedís algo
para lo que no tenés permiso, te lo dice en vez de mostrarlo. Si te dan un
permiso nuevo, pedile a Claude "revisá mis permisos" para que lo tenga en
cuenta.

---

## Qué puede hacer: las 8 herramientas

Claude las elige solo según lo que le pedís.

| Herramienta | Qué hace |
|---|---|
| `buscar_endpoint` | Busca qué endpoint de Finnegans sirve para tu pedido, en el swagger y en la documentación a la vez. |
| `ver_endpoint` | Muestra los métodos, parámetros y campos de un endpoint o recurso. |
| `leer` | Lee datos de Finnegans (GET); si son muchos, los carga en una tabla de trabajo. |
| `consultar` | Consulta con SQL de solo lectura las tablas ya cargadas, por páginas. |
| `exportar` | Guarda el resultado de una consulta como Excel o CSV en la carpeta de exportación. |
| `escribir` | Modifica datos en Finnegans (POST, PUT, PATCH o DELETE) y muestra qué cambió. |
| `guia` | Explica reglas del negocio: sucursales, IIBB, rutas, tipos de endpoint, escrituras, clientes y parámetros de reportes. |
| `verificar_conexion` | Comprueba las claves y la conexión, dice cuál falla y cuándo se revisaron tus permisos. Si le pedís "revisá mis permisos", los revisa de nuevo. |

Las lecturas y las escrituras son herramientas separadas a propósito, para que
Claude Desktop pueda pedirte permiso solo cuando se va a modificar algo.

### Permisos recomendados en Claude Desktop

En Configuración, Extensiones, Finnegans, ajustá el permiso de cada herramienta:

- **Permitir siempre**: `buscar_endpoint`, `ver_endpoint`, `leer`, `consultar`,
  `exportar`, `guia` y `verificar_conexion`. Son de solo lectura (`exportar`
  solo escribe un archivo en tu carpeta de exportación).
- **Preguntar siempre**: `escribir`. Es la única que cambia datos en Finnegans,
  y se ejecuta apenas la aprobás: leé bien lo que Claude va a mandar antes de
  tocar **Permitir**.

---

## Actualizar

Cuando haya una versión nueva, Juan Sbatella te pasa el `finnegans.mcpb`
actualizado.

- Si lo instaló el Owner para el equipo: el Owner sube el archivo nuevo y
  reemplaza al anterior.
- Si lo instalaste vos: abrí el archivo nuevo con doble clic y confirmá el
  reemplazo.

Las claves cargadas se conservan. Si Juan Sbatella te avisa que cambió el
formulario, Claude Desktop te va a pedir los campos nuevos.

---

## Desarrollo

Requisitos: Python 3.12 o superior, [uv](https://docs.astral.sh/uv/) y Node.js
(solo para empaquetar).

```bash
uv sync                          # instala dependencias
uv run pytest                    # corre los tests
```

Para generar el instalable usá el script de empaquetado. La clave del swagger
de la empresa se toma de la variable de entorno `FINNEGANS_SWAGGER_KEY` (nunca
de un archivo) y queda precargada solo en el paquete, no en el repo:

```bash
FINNEGANS_SWAGGER_KEY=... uv run python scripts/empaquetar.py [--salida finnegans.mcpb]
```

- `src/finnegans_core/`: la lógica (cliente de Finnegans, catálogo, tablas de
  trabajo, exportación, guía de negocio).
- `src/finnegans_mcp/`: el servidor MCP con las 8 herramientas.
- `manifest.json`: la ficha de la extensión y su formulario de instalación.
- `.mcpbignore`: lo que no viaja dentro del paquete (tests, docs, exportaciones
  y cualquier archivo local).

Los tests usan claves y respuestas falsas: no necesitan acceso a Finnegans.
`npx @anthropic-ai/mcpb validate manifest.json` comprueba el manifest antes de
empaquetar. El `.mcpb` generado no se versiona.
