"""Canal Digital: clusters de productos y reposicion para una bodega (hoy la 430).

Este paquete es el NUCLEO PURO del modulo: Python estandar, sin base de datos, sin
polars ni pandas y sin importar nada del resto de la plataforma. Lo van a reutilizar
la API (tablas `canal_digital_*`, rutas y pantallas) y el script que arma el Excel de
la primera version, para que los dos calculen exactamente lo mismo.

  politica       las 27 filas de politica por cluster (Frecuencia-Piezas-Valor).
  clasificacion  frecuencia, Pareto de piezas y de valor, NUEVO / SIN MOVIMIENTO,
                 resumen por cluster y validaciones.
  reposicion     D, sigma, SS, S, posicion y sugerido de un producto.
  paso_a_paso    el recorrido de un producto en frases legibles.
  numeros        ayudas numericas y de fechas compartidas.

Las decisiones del dueno (20-10-2026) estan en el plan "Canal Digital - plan y
cruces". Los parametros que siguen provisorios (politica, minimo y multiplo,
comprometido) estan marcados como tales en cada modulo.
"""
