# Herramientas de la lista de precios

Scripts de migración y mantención del módulo de precios. **No son parte del
servicio**: se corren a mano desde un PC con acceso al Excel maestro y a la API.
Se guardan aquí porque son la única forma de reproducir lo que hay en producción.

El maestro vive en
`OneDrive - Curifor S.A\Documentos\Desarrollos\Precios Curifor\LISTA DE PRECIOS.xlsx`
(hoja `Lista sin duplicados`).

## Orden normal de uso

```bash
# 1. Del Excel a CSV (deja seed/*.csv junto al script)
python semillas.py

# 2. De los CSV a la plataforma. Siembra politica + rubros + no-productos,
#    carga la lista en tandas de 5.000 y recalcula.
python push_precios.py --env "ruta\al\.env"        # PLATAFORMA_API_URL/EMAIL/PASSWORD
python push_precios.py --api http://localhost:8000 --email x --password y

# 3. Si el Excel se depuro y la plataforma quedo con productos de mas:
python borrar_en_plataforma.py --simular           # dice cuantos y cuales
python borrar_en_plataforma.py
```

`borrar_en_plataforma.py` no se fía de una lista guardada: compara los códigos
de la plataforma contra `seed/lista.csv` y borra la diferencia, en lotes de 500.

## Depurar el Excel

`set_2025.py` calcula qué productos salen (stock 0 + última venta anterior a un
corte, respetando tránsito, compras recientes, ventas bajo otro rubro y los que
tienen Congelar o Precio Fijo). `borrar_filas2.py` borra esas filas del xlsx
conservando todo lo demás byte a byte, y `verif_borrado2.py` lo comprueba con un
hash por columna antes de instalar el archivo.

## Dos trampas que cuestan tiempo

**Inspección TLS.** En la red de Curifor el proxy firma los certificados con un
CA propio: Python falla con `CERTIFICATE_VERIFY_FAILED` y `curl` no conecta.
`push_precios.py` usa `truststore`, que valida contra el almacén de Windows —la
verificación sigue activa, no se desactiva—. Cualquier script nuevo que hable
con la API debe importar `CTX` de `push_precios` y pasarlo a `urlopen`.

**Recargar completo se cae.** `POST /api/admin/precios/cargar` con
`reemplazar=true` borra las 60 mil filas e inserta otras tantas en una sola
transacción, y Supabase devuelve 500 por timeout (la transacción hace rollback
limpio, no deja nada a medias). Para depurar hay que usar
`/api/admin/precios/eliminar`, no recargar.
