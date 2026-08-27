# Módulo de Gestión de Comisiones Supricom (`supricom_commissions`)

## Descripción General
Este módulo para Odoo 17 gestiona el cálculo, liquidación y análisis de comisiones de ventas para **Supricom**. Está diseñado para manejar lógica compleja de cumplimiento de metas, penalizaciones, deducciones de gastos y reglas específicas por país (Venezuela y Panamá) y rol jerárquico.

## Características Principales

### 1. Configuración de Vendedores y Metas
- **Tipos de Vendedores**: Clasificación por tipos (ej. Vendedor, Gerente) con asignación de país (VEN/PAN) y roles gerenciales específicos (Gerente de Ventas, Gerente de Operaciones).
- **Metas Mensuales**: Definición de metas monetarias por vendedor y mes.
- **Matriz de Comisiones**: Tabla configurable que define el % de comisión base según el % de cumplimiento de la meta.

> [!IMPORTANT]
> **Configuración de Porcentajes**:
> A partir de la versión 1.2, todos los porcentajes (Matriz, Gastos Fijos, Penalizaciones) se manejan como **RATIOS (0.00 - 1.00)**.
> - Para **3%**, introduzca: `3` (el sistema lo guardará como 0.03 y mostrará 3%).
> - Para **100%**, introduzca: `100`.
> - **Verifique sus configuraciones antiguas** si ve valores como "300%".

### 2. Control de Ventas
- **Precio Mínimo**:
  - Validación en Líneas de Pedido que impide vender por debajo del `min_price` del producto (requiere permisos de Administrador para confirmar).
  - Flag `is_min_price_sale` que se propaga desde el Pedido hasta la Factura y Líneas de Comisión.
- **Comisiones Especiales**: Configuración en el producto para usar tarifas fijas independientes de la matriz de cumplimiento.

### 3. Lógica de Cálculo Avanzada
El cálculo se basa en **Pagos Recibidos** (Cobranza efectiva) y aplica las siguientes reglas:

- **Soporte Multi-Moneda y Dualidad ($/Bs)**:
  - **Facturas en Dólares ($)**: El sistema calcula la comisión directamente en USD (Base USD * % Comi) para evitar errores de conversión. La columna **"Monto Comisión ($)"** muestra el valor exacto.
  - **Facturas en Bolívares (Bs)**: El sistema calcula en Bs y convierte el resultado final a USD (usando la tasa histórica de la fecha de la factura/pago) para mostrarlo en la columna referencial **"Monto Comisión ($)"**.
  - **Conversión de Costos**: Si el costo del producto está en una moneda diferente a la factura (a.e. Costo en Bs, Venta en $), el sistema convierte el costo a la moneda de la factura _antes_ de calcular la Base, asegurando un margen real.

- **Datos Históricos**:
  - El sistema detecta automáticamente ventas antiguas (anteriores a la instalación del módulo) que no tienen los campos de comisión guardados.
  - Para estas ventas, recalcula dinámicamente la Base (Subtotal - Costo Estándar) al momento de generar la liquidación.

- **Validación de Pagos Vencidos**:
  - Las facturas pagadas después de la fecha de vencimiento NO suman para la meta ni generan comisión, a menos que se active el check manual "Vencido (check)" en la factura (con permiso de Gerente).
  - **Log de Auditoría ("Log de Excepciones")**:
    - Herramienta de control que registra automáticamente cuándo un Gerente autoriza el pago de una factura vencida.
    - Guarda: Usuario, Fecha, Hora y Motivo.
    - Genera alertas de recálculo si la autorización afecta las metas del mes.
  
- **Deducción de Gastos Fijos**: Cálculo automático de un % de deducción (prorrateo) basado en los gastos fijos de la empresa en el periodo.

### 4. Reglas Específicas para Gerentes
El sistema distingue y aplica reglas de negocio automáticas por región y rol:

- **Gerente de Operaciones (Panamá)**:
  - Comisión Fija del **0.15%** sobre el volumen total de ventas cobradas en el país.
  - No depende de metas.

- **Gerente de Ventas (Venezuela)**:
  - Comisión Fija del **0.20%** sobre el volumen total de ventas cobradas por su equipo.

- **Gerente de Ventas (Panamá)**:
  - Comisión Variable (**0.10% - 0.20%**) basada en el cumplimiento de la meta grupal:
    - **cumplimiento > 110%**: 0.20%
    - **cumplimiento > 100%**: 0.15%
    - **cumplimiento > 80%**: 0.10%
    - **cumplimiento < 80%**: 0.00%

### 5. Penalizaciones Dinámicas
- **Penalización por Precio Mínimo**:
  - Al generar la liquidación, el Gerente puede establecer un % de penalización (ej. 10%).
  - Este porcentaje se descuenta automáticamente de la comisión de los productos vendidos a precio mínimo.

### 6. Proceso de Liquidación y Análisis
- **Wizard de Generación**: Asistente para calcular comisiones de un rango de fechas.
  - Genera registros persistentes (`commission.settlement`) para historial.
  - "Congela" los datos al momento del cálculo (Snapshot).
- **Vistas de Análisis**:
  - **Pivot**: Tabla dinámica para analizar comisiones por Vendedor, Cliente, Producto, Mes y País.
  - **Gráfico**: Visualización de tendencias de pago.

### 7. Reportes (PDF)
- **Reporte Detallado**: Desglose línea por línea por vendedor, incluyendo Términos de Pago, % Comisón, % Deducción, % Penalización y total a pagar.
- **Reporte Consolidado**: Resumen ejecutivo para el departamento de finanzas con totales por vendedor y gran total.

## Seguridad
- **Grupos de Usuario**:
  - `Usuario`: Puede ver sus propias comisiones.
  - `Gerente de Comisiones`: Puede configurar matrices, autorizar pagos vencidos, ver logs y generar liquidaciones.

## Flujo de Trabajo Típico
1. Configurar Metas Mensuales y Matriz.
2. Ventas y Facturación (validación automática de precio mínimo).
3. Registro de Pagos (validación automática de fechas de vencimiento).
4. (Opcional) Gerente autoriza pago vencido en la factura -> Se genera Log.
5. Fin de Mes: Gerente ejecuta "Generar Liquidación".
   - Define penalización por precio mínimo.
   - Revisa reportes Pivot/Gráfico.
6. Imprimir PDF Consolidado para pago.
