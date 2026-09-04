# Lista de precios

La lista que se sube al ERP, viva en la plataforma. Reemplaza al Excel
`LISTA DE PRECIOS.xlsx` y al `.exe` que corria en el PC de Hugo: la regla es la
misma, pero corre donde estan los datos (stock, costo, compras y ventas que la
plataforma ya recibe del motor) y las decisiones de las personas quedan en una
tabla que ningun job toca.

Pantallas: `/precios` (la lista) y `/precios/politicas` (factores y rubros).

## Como se decide el precio

En este orden; gana el primero que aplica (`services/precios_service.calcular`):

1. **Precio fijo** (decision humana): ese es el precio, pase lo que pase.
2. **Congelado** (decision humana): el precio que tenia al congelar, aunque el
   costo cambie despues.
3. **Stock 0 y nada en transito**: precio 0 (el ERP no lo ofrece).
4. **No es producto** (servicios, mano de obra): sin precio.
5. **Tipo Sugerido**: la lista del proveedor (Gildemeister).
6. **El resto**: `ROUND(costo x factor)`, redondeando como Excel (la mitad hacia
   arriba).

El **factor** sale de la politica por (tipo, procedencia).

El **tipo** se decide: escrito a mano > la glosa empieza con `NEU` (neumatico) >
el tipo del rubro (`politica_rubro`).

La **procedencia**: escrita a mano > procedencia forzada del rubro > ultima
compra (si la mas reciente esta en el seguimiento de importacion es Importado;
si esta en el nacional, Nacional) > lo que dice el maestro del ERP > `SIN
REVISION` (queda sin precio hasta que alguien decida).

## Las tablas

| Tabla | Que es | Quien la escribe |
|---|---|---|
| `precio_producto` | Una fila por producto con todo lo calculado. Se pisa en cada recalculo. `origen` distingue lo que vino del ERP (`maestro`) de lo creado en la plataforma (`manual`): una recarga del maestro borra solo lo primero. | el recalculo y las cargas |
| `precio_override` | Precio fijo, congelar, tipo/procedencia a mano, "no es producto", observacion. | solo personas |
| `politica_precio` | Factor por (tipo, procedencia). | admin |
| `politica_rubro` | Tipo y procedencia forzada por rubro. | admin |
| `precio_cambio` | Que cambio en cada recalculo (procedencia, costo, stock, precio, tipo), pendiente hasta que alguien lo marca visto. | el recalculo |
| `precio_envio` | Que precio y costo se mando al ERP, cuando y quien. Es lo que hace posible exportar solo las diferencias. | la exportacion |

## Permisos

- Ver y exportar: cualquiera de Abastecimiento.
- Editar un precio, crear un producto, recalcular, marcar cambios vistos:
  admin o email en `EMAILS_PRECIOS` (variable de entorno, separada por comas).
- La politica: solo admin.

## Cargas

- **Primera carga** desde el Excel: `POST /api/admin/precios/politica` (factores,
  rubros, no-productos, precios sugeridos) y `POST /api/admin/precios/cargar` por
  tandas. Lo humano del Excel (Obs Precio + Precio Fijo, Congelar) se convierte
  en overrides. Un Precio Fijo sin Obs se ignora, igual que lo ignora la
  formula del Excel.
- **Compras** (la regla de procedencia): `POST /api/admin/precios/compras` con
  la ultima recepcion importada y el ultimo P/E nacional por producto. Fusiona:
  nunca borra una fecha.
- **Costos**: `POST /api/admin/precios/costos` con `{producto, costo}` de TODOS
  los productos (columna Costo del Excel de stock del ERP), en la misma corrida
  en que el motor publica el stock. Para lo que el sugerido evalua, ademas manda
  `dim_producto.costo_unitario` (lo reconstruye `cargar-sugerido`). NO se usa
  `producto_catalogo.costo`: es una carga unica sin fecha.
- **Stock, precio del proveedor y ultima venta** los toma el recalculo de las
  tablas que el motor ya publica (`stock_unificado`, `stock_transito`,
  `sugerido`, `venta_historica`).

## Exportar al ERP

`GET /api/precios/exportar?formato=erp` genera `SKU | Precio_Optimo | Costo`,
igual que el `.exe`. Con `solo_diferencias=true` salen solo los productos cuyo
precio o costo difiere de lo ultimo enviado (o nunca enviados). Cada
exportacion queda registrada en `precio_envio`.
