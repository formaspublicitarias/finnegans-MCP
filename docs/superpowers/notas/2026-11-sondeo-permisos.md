# Sondeo de permisos de reportes y autoria (spike de la fase 1)

## Cómo correrlo

Es solo lectura: hace únicamente GET. Las claves van por variables de entorno, nunca desde un `.env`:

- `FINNEGANS_CLIENT_ID`
- `FINNEGANS_CLIENT_SECRET`
- `FINNEGANS_SWAGGER_KEY`
- `FINNEGANS_DOCS_CLIENT_ID`
- `FINNEGANS_DOCS_SECRET_KEY`

Desde la raíz del repo:

```
.\.venv\Scripts\python.exe scripts\sondeo_permisos.py --sin-autoria
.\.venv\Scripts\python.exe scripts\sondeo_permisos.py --reportes DETALLETRANSACCIONES
```

El script hace tres cosas:

1. **Censo de reportes.** Cuenta los reportes del swagger sin llamar a la API y los separa en tres grupos:
   - con algún parámetro requerido;
   - sin requeridos pero con rango de fechas;
   - sin requeridos ni rango.
2. **Prueba del truco de fechas.** En los primeros N reportes sin requeridos y con rango (por defecto 4) prueba solo dos candidatos: "desde posterior a hasta" y "rango de 1 día". Nunca los llama sin parámetros, porque eso podría ejecutar el reporte entero.
3. **Reportes puntuales.** Con `--reportes`, prueba los cuatro candidatos en esos reportes.

## Resultados

### Corrida 1 (2026-11-19, cuenta con permisos completos)

**DETALLETRANSACCIONES.** Parámetros de fecha: `PARAM_Fechadesde`, `PARAM_Fechahasta`.

| Candidato | HTTP | Segundos | Respuesta |
|---|---|---|---|
| a) sin parámetros | 400 | 0.9 | `Parameter PARAM_Categoria is mandatory` |
| b) fechas inválidas | 400 | 0.2 | ídem |
| c) desde posterior a hasta | 400 | 0.2 | ídem |
| d) rango de 1 día | 400 | 0.2 | ídem |

**Autoría:**

- `cliente` solo trae `FechaAlta`. No tiene usuario de alta ni de modificación.
- Los paths del swagger que coincidieron con la búsqueda (`/apicatalog/{codigo}`, `/reports/getClaseVOFromApiCatalog`) son el catálogo de APIs, no una auditoría.

### Corrida 2 (2026-11-19, cuenta con permisos completos)

**Censo de los 238 reportes del swagger:**

| Grupo | Cantidad |
|---|---|
| Con algún parámetro requerido | 101 |
| Sin requeridos, con rango de fechas | 56 |
| Sin requeridos ni rango de fechas | 81 |

**Truco "desde posterior a hasta"** (2099-01-02 / 2099-01-01) en los cuatro primeros reportes del segundo grupo:

| Reporte | HTTP | Segundos | Respuesta |
|---|---|---|---|
| AjusteDeStockSistemaIsma | 200 | 1.1 | `[]` |
| ANAFACTURACION | 200 | 0.5 | `[]` |
| analisisCasosDirectos | 200 | 0.6 | `[]` |
| analisisCobranza | 200 | 0.5 | `[]` |

El candidato "rango de 1 día" devolvió filas reales: no se transcribe porque trae datos del negocio.

## Lo que se aprendió

- **Un reporte con un parámetro requerido es barato de sondear.** Llamado sin ese parámetro, Finnegans contesta `400 … is mandatory` en menos de un segundo, sin ejecutar el reporte. Una cuenta sin permiso recibe `403 Prestacion sin permiso` antes de esa validación, como se verificó el 2026-11-17. Entonces, para estos reportes:
  - 400 quiere decir **permitido**;
  - 403 "sin permiso" quiere decir **denegado**.
- **El truco de fechas funciona.** En un reporte sin requeridos pero con rango, "desde posterior a hasta" contesta `[]` en 0.5 a 1.1 s: un rango imposible no trae datos y es barato. Una cuenta sin permiso recibe 403 antes de mirar los parámetros.
- **Autoría (spec §5.6):** Finnegans no registra en el cliente quién lo modificó. "Quién hizo qué" queda para el registro de cambios de la fase 2.

## Decisiones (aplicadas en `src/finnegans_core/escaneo.py`)

El escaneo automático y el pedido con "revisá mis permisos" cubren 157 de los 238 reportes, sin ejecutar ninguno:

- **Con un parámetro requerido (101):** se sondean sin parámetros, y el 400 cuenta como permitido.
- **Sin requeridos y con rango (56):** se sondean con "desde posterior a hasta".
- **Sin requeridos ni rango (81):** se aprenden al usarlos. Revisarlos los ejecuta, así que solo entran con `incluir_reportes=True` y `confirmar=True`, y el aviso habla de "unos 80".

`REPORTES_EN_ESCANEO_AUTOMATICO` queda en `False`: ahora se refiere solo a esos 81.

`guia/escrituras.md` no cambia, porque Finnegans no trae el usuario que edita.
