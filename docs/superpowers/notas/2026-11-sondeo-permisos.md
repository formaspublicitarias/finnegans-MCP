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

### Corrida 2

pendiente: censo y prueba del truco de fechas en reportes sin requeridos.

## Lo que se aprendió

- **Un reporte con un parámetro requerido es barato de sondear.** Llamado sin ese parámetro, Finnegans contesta `400 … is mandatory` en menos de un segundo, sin ejecutar el reporte. Una cuenta sin permiso recibe `403 Prestacion sin permiso` antes de esa validación, como se verificó el 2026-11-17. Entonces, para estos reportes:
  - 400 quiere decir **permitido**;
  - 403 "sin permiso" quiere decir **denegado**.
- **El truco de fechas todavía no se midió.** `DETALLETRANSACCIONES` cortó en `PARAM_Categoria` antes de mirar las fechas, así que los candidatos (b), (c) y (d) no se pudieron evaluar. La corrida 2 los prueba en reportes sin requeridos.
- **Autoría (spec §5.6):** Finnegans no registra en el cliente quién lo modificó. "Quién hizo qué" queda para el registro de cambios de la fase 2.

## Decisiones

Hasta la corrida 2 siguen los valores conservadores:

- `SONDA_REPORTE = {}`
- `REPORTES_EN_ESCANEO_AUTOMATICO = False`

Después de la corrida 2:

- **Reportes con un parámetro requerido:** el escaneo automático los incluye, sondeados sin parámetros.
- **Reportes sin requeridos y con rango:** el escaneo los incluye con la sonda "desde posterior a hasta", solo si responde en menos de 3 s en todos los reportes probados y con un estado distinto de 403.
- **Reportes sin requeridos ni rango:** se siguen aprendiendo al usarlos.

`guia/escrituras.md` no cambia, porque Finnegans no trae el usuario que edita.
