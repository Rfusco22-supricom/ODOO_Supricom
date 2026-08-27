# Gestión de Incentivos de Ventas (SPIFF)

Este módulo permite la gestión y cálculo automatizado de incentivos de ventas conocidos como "SPIFFs" (Sales Performance Incentive Fund). Facilita la creación de reglas de incentivos basadas en productos específicos o marcas, y calcula las comisiones correspondientes para los vendedores.

## Características Principales

*   **Reglas Flexibles**: Definición de incentivos por:
    *   **Producto**: Una cantidad fija por cada unidad vendida.
    *   **Marca**: Un monto fijo por cada bloque de venta alcanzado (Ej. $100 de bono por cada $5,000 vendidos de la marca X).
*   **Cálculo Automático**: Procesa facturas y rectificativas (devoluciones) publicadas en un periodo determinado.
*   **Soporte de Marcas**: Compatibilidad con el campo `x_studio_marca` y un campo de respaldo nativo `brand_name` en el producto.
*   **Reportes Detallados**: Generación de líneas de cálculo por vendedor y regla aplicada, mostrando la venta neta y el monto a pagar.
*   **Gestión de Devoluciones**: Las notas de crédito restan de la cantidad o monto vendido, asegurando que solo se paguen incentivos sobre ventas netas reales.

## Configuración

### 1. Definir Reglas de SPIFF
Vaya al menú correspondiente (según la configuración de vistas) para crear reglas de incentivos (`spiff.incentive`):

*   **Referencia**: Nombre descriptivo de la regla.
*   **Fechas**: Defina el rango de fechas (`Fecha Inicio` y `Fecha Fin`) durante el cual la regla estará activa.
*   **Tipo de Regla**:
    *   **Por Producto**: Seleccione el producto y el "Incentivo por Unidad".
    *   **Por Marca**: Escriba el nombre de la "Marca" (debe coincidir textualmente), el "Bloque de Monto Objetivo" y el "Incentivo por Bloque".

### 2. Configuración de Productos (Solo para reglas de Marca)
Para que las reglas por marca funcionen, los productos deben tener asignada una marca. El sistema busca la marca en el siguiente orden:
1.  Campo personalizado `x_studio_marca`.
2.  Campo nativo del módulo `brand_name` (pestaña "Ventas" o "Información General" en el formulario del producto, dependiendo de la vista).

## Uso

### Generar un Cálculo
1.  Vaya al menú de Cálculos de SPIFF (`spiff.calculation`).
2.  Cree un nuevo registro.
3.  Establezca el **Inicio Periodo** y **Fin Periodo**.
4.  Guarde y haga clic en el botón de acción para calcular.
5.  El sistema buscará todas las facturas publicadas en ese rango de fechas.
6.  En la pestaña **Resultados**, verá el desglose por vendedor:
    *   **Cant. Neta**: Unidades vendidas menos devueltas.
    *   **Monto Neto Vendido**: Total monetario vendido menos devoluciones.
    *   **Pago SPIFF**: El monto total de incentivo calculado.

## Detalles Técnicos

*   **Dependencias**: `sale_management`, `account`.
*   **Modelos**:
    *   `spiff.incentive`: Configuración de reglas.
    *   `spiff.calculation`: Cabecera del cálculo.
    *   `spiff.calculation.line`: Detalle de líneas calculadas.
    *   `product.template`: Extensión para agregar campo de marca.
