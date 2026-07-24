# Cómo se calcula el sugerido de compras (Curifor)

> Documentación de negocio del modelo. Es el MISMO contenido que el módulo "Modelo"
> de la plataforma (`apps/web/app/modelo/page.tsx`) y el `.docx` de referencia. Explica,
> en lenguaje simple, de dónde sale cada número del sugerido. Si el modelo cambia, hay
> que actualizar los tres lugares.

## Qué hace el modelo

A partir del historial de ventas, el stock actual, las órdenes de compra y los tiempos
de entrega de cada proveedor, el modelo estima cuánto se vende y cuánto stock hace falta
para no quebrar, y con eso calcula cuánto **pedir** (al proveedor) o cuánto **trasladar**
(desde el Centro de Distribución, CD) en cada producto y sucursal.

El cálculo es una cadena de 8 etapas; cada una usa el resultado de la anterior:

1. Limpiar las ventas
2. Clasificar cada producto (ABC)
3. Estimar la demanda
4. Asignar proveedor y tiempo de entrega
5. Decidir si se abastece por el CD
6. Calcular el stock de seguridad
7. Calcular el sugerido de compra
8. Repartir el stock del CD (traslados)

## De dónde salen los datos

- **Ventas (Curifor + Frontera):** el historial de venta mensual por producto y sucursal. Base para clasificar y estimar la demanda.
- **Seguimiento de compras (OC):** las órdenes de compra: proveedor, fechas de OC y recepción (para el lead time) y lo que está en tránsito.
- **Stock por bodega (Curifor + Frontera):** el stock disponible hoy en cada sucursal y en el CD.
- **Catálogos y reemplazos:** descripción, marca, unidad, región de la sucursal y qué códigos son reemplazo de cuál (se tratan como un mismo producto).

## 1 · Limpieza de las ventas

Antes de calcular nada, se depura la venta para que el número sea real y comparable:

- **Venta neta:** se descuentan devoluciones y notas de crédito (no la venta bruta).
- **Solo meses cerrados:** se ignora el mes en curso (incompleto).
- **Reemplazos agrupados:** si un código reemplaza a otro, su venta y stock se suman al producto "maestro".
- **Sucursales excluidas:** las cerradas o fuera de alcance (La Florida, Lira, Lo Blanco, los Mall Plaza, Ovalle (3), Gran Avenida, Coquimbo y Diez de Julio antigua).
- **Productos internos excluidos:** conceptos que no se compran a proveedor (taller D&P, insumos mecánica, incentivos, deducciones).
- **Categorías excluidas:** Colisión y Campañas no participan del sugerido de reposición.
- **Ventas móviles y canales al CD:** Linderos "venta móvil", Canal Digital y Oficinas Centrales se consolidan en el CD.

Para las **compras** (proveedor y tránsito) se usan solo las OC con motivo **"reposición"**; las compras puntuales (colisión, garantía, calzada) no cuentan como abastecimiento normal.

## 2 · Clasificación ABC (por frecuencia de venta)

No es un ABC de Pareto (por facturación). Acá la clase mide **con qué frecuencia se vende**: se cuentan los meses con venta en los últimos 3, 6 y 12 meses.

- **A:** 5 o 6 de los últimos 6 meses → muy frecuente.
- **B:** 4 de los últimos 6 meses → frecuente.
- **C:** 3 de los últimos 6 (con apoyo en 3m o 12m) → intermitente.
- **D:** el resto → esporádico / casi sin venta.

Se calcula en dos niveles: **local** (el producto en esa sucursal) y **agregada** (el producto en toda la empresa). La combinación de ambas decide si conviene centralizar el producto en el CD. La clase define casi todo lo que sigue: cuántos meses de historia se miran, cuánto colchón se exige y si se compra directo o vía CD.

## 3 · Demanda mensual

Es el motor del cálculo: cuántas unidades por mes se espera vender.

- **Ventana según clase:** los A/B miran los últimos 6 meses; los C/D, los últimos 12.
- **Se arma la serie mensual** (la venta de cada mes; 0 en los meses sin venta).
- **Winsorización:** se recortan los meses atípicamente altos con un tope robusto (mediana + k × 1,4826 × MAD, con **k = 3**) para que un pedido puntual no infle la demanda.
- **Demanda mensual = promedio** de la serie ya recortada; la **demanda diaria = demanda mensual ÷ 22 días hábiles**.
- **Caso CD:** para los productos que el CD centraliza, la demanda consolida su venta más la de las sucursales que se abastecen de él, sobre 12 meses.

## 4 · Proveedor y tiempo de entrega (lead time)

**Proveedor:** se toma el de la orden de compra de reposición más reciente de ese producto en esa sucursal. Si esa sucursal nunca lo compró por reposición, se completa con el proveedor que el modelo deduce del histórico del producto (válido porque cada código tiene un único proveedor).

**Lead time** (días que tarda en llegar): se calcula desde el seguimiento, midiendo los días entre la OC y su recepción, descartando la cola de casos lentos y promediando el resto. Jerarquía:

- el lead time de ese proveedor en esa sucursal (si hay historial);
- si no, el lead time general de ese proveedor;
- si tampoco hay, 8 días por defecto.

**Lead time del CD a la sucursal:** 1 día en la Región Metropolitana, 2 en el resto (casos fijos: Diez de Julio (2) = 1, Talca (2) = 2). El **lead time efectivo** es el del CD si el producto se abastece por el CD, o el del proveedor si se compra directo.

## 5 · ¿Se abastece por el Centro de Distribución?

Algunos productos conviene centralizarlos en el CD y desde ahí distribuir, en vez de que cada sucursal le compre al proveedor:

- **En una sucursal:** se abastece por el CD si el producto es importado, o si es de baja rotación local (C/D) pero de alta rotación a nivel empresa (agregada A/B).
- **En el CD:** solo se abastece a sí mismo si el producto es importado.

Esta decisión cambia el ciclo de orden y el lead time efectivo, y habilita los traslados (etapa 8).

## 6 · Stock de seguridad

Es el colchón para no quebrar mientras llega la reposición, frente a la variabilidad de la venta:

**Stock de seguridad = Z × desviación × √(meses de protección)**

- **Z (nivel de servicio) por clase:** el nivel de servicio es la probabilidad de NO quebrar stock durante la ventana de protección; Z lo traduce a colchón. A = 1,645 (95 %) · B = 1,282 (90 %) · C = 0,842 (80 %) · D = 0 (sin colchón). Importado por CD, con nivel reducido porque el CD consolida la variabilidad de varias sucursales: A = 1,282 (90 %) · B = 1,036 (85 %). Cuanto más importante el producto, más alto el nivel de servicio.
- **Desviación:** cuánto varía la venta mes a mes (de la misma serie ya winsorizada).
- **Meses de protección = (lead time efectivo + ciclo de orden) ÷ 22.** El ciclo de orden es **5 días, tanto en compra directa como vía CD** (unificado el 24-jul-2026; antes era 3 vía CD).

En criollo: productos importantes y de venta irregular llevan más colchón; los parejos o de baja clase, menos o nada.

## 7 · El sugerido de compra

Con la demanda, el lead time y el colchón se calcula la necesidad y se descuenta lo que ya se tiene:

**Necesidad = Demanda diaria × (ciclo orden + lead time) + Stock seguridad − Stock actual − En tránsito**

- **Stock actual:** lo disponible hoy en la sucursal (sumando el grupo de reemplazos, Curifor + Frontera).
- **En tránsito:** las OC pendientes que ya vienen en camino (nacional de reposición hasta 30 días, importado hasta 180, frontera hasta 30).
- **Sugerido:** esa necesidad (nunca negativa), pero solo se sugiere comprar en productos cuya clase que compra es A/B; los de baja clase quedan en 0.
- **Punto de pedido = Demanda diaria × lead time + Stock seguridad.** Indica *cuándo* reponer (no cuánto).
- **Pedir:** la fila queda "Sí" cuando el sugerido es mayor que 0.

## 8 · Distribución desde el CD y traslados

Para los productos centralizados, antes de comprarle al proveedor se reparte el stock que ya está en el CD:

- **Reparto por prioridad:** el stock del CD se asigna a las sucursales elegibles siguiendo un ranking fijo. Cada una recibe hasta cubrir su necesidad, con lo que quede después de las de mayor prioridad.
- **Comprar en el CD:** se marca "Sí" cuando, al llegar el turno de una sucursal, la necesidad acumulada supera el stock del CD (señal de que el CD debe reponerse).
- **Compra neta:** el sugerido menos lo que se cubre con traslado desde el CD. Es lo que efectivamente hay que comprarle al proveedor.
- **Traslado lateral (informativo):** para las filas con sugerido, se listan otras sucursales con stock del producto, por si conviene un traslado en vez de comprar.

**Orden de prioridad del CD** (ranking fijo): 1 Diez de Julio (2), 2 Brasil 18, 3 Linderos, 4 Placilla, 5 Rancagua, 6 Rancagua 2, 7 Curicó, 8 Talca, 9 Talca (2), 10 Chillán, 11 Chillán Viejo. El resto queda en prioridad más baja.

## Reglas de negocio adicionales

Sobre el cálculo del modelo, la plataforma aplica algunos ajustes de sentido común:

- **Stock cubre + sin venta reciente → no pedir:** si una sucursal tiene stock suficiente para su demanda mensual y no vendió el producto el mes anterior, no se sugiere comprar.
- **Sucursales cerradas ocultas:** la Diez de Julio antigua (cerrada) no se muestra; solo la Diez de Julio (2) activa.
- **Proveedores rellenados:** los productos sin reposición confirmada en la sucursal muestran igual el proveedor deducido, para reducir las filas "sin proveedor".
- **Aceites en mililitros:** se mantienen como vienen (decisión de Abastecimiento); pueden inflar totales pero es esperado.

## Parámetros y clasificaciones de referencia (auditados jul-2026)

- **Escalar winsorización (k):** 3 — qué tan estricto es el recorte de meses pico (antes 1).
- **Días hábiles por mes:** 22 — divisor para pasar de demanda mensual a diaria.
- **Ciclo de orden:** 5 días (directo y vía CD) — días de cobertura extra que se agregan al pedir.
- **Lead time por defecto:** 8 días — cuando no hay proveedor ni historial de OC.
- **Lead time CD → sucursal:** 1 (RM) / 2 (resto) — días de traslado del CD a la sucursal.
- **Vigencia de tránsito:** 30 d nacional / 180 d importado — ventana para contar una OC como "en camino".
- **Nivel de servicio Z:** A = 1,645 · B = 1,282 · C = 0,842 · D = 0 — colchón por clase (más alto = más stock de seguridad).
