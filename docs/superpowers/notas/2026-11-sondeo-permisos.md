# Sondeo de permisos de reportes y autoria (spike de la fase 1)

## Cómo correrlo

Solo lectura (solo GET). Las claves van por variables de entorno, nunca desde un `.env`
(`FINNEGANS_CLIENT_ID`, `FINNEGANS_CLIENT_SECRET`, `FINNEGANS_SWAGGER_KEY`,
`FINNEGANS_DOCS_CLIENT_ID`, `FINNEGANS_DOCS_SECRET_KEY`). Desde la raiz del repo:

```
uv run python scripts/sondeo_permisos.py --reportes DETALLETRANSACCIONES,<2 a 4 reportes pesados mas>
```

Para cada reporte prueba cuatro candidatos (sin parametros, fechas invalidas, desde posterior
a hasta, rango de 1 dia) y muestra estado HTTP, segundos y los primeros 120 caracteres de la
respuesta redactada. Despues lista los nombres (sin valores) de los campos de autoria de un
cliente y los paths del swagger que parecen de auditoria. Pegar la salida abajo, sin valores.

## Resultados

pendiente: lo corre Juan

## Decisiones

Hasta que la corrida diga otra cosa, valen los valores conservadores:

- `SONDA_REPORTE = {}`
- `REPORTES_EN_ESCANEO_AUTOMATICO = False`

Regla para cambiarlos: `SONDA_REPORTE` es el candidato mas barato que responde en menos de 3 s
en todos los reportes pesados y con estado distinto de 403 para una cuenta con permiso. Solo si
existe, `REPORTES_EN_ESCANEO_AUTOMATICO = True`.

Autoria (spec 5.6): pendiente. Si los registros traen el usuario que los edito, la tarea 6
agrega un parrafo a `guia/escrituras.md` sobre como consultarlo.
