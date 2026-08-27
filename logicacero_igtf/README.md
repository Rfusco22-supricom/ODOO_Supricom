# Módulo Logica Cero IGTF (`logicacero_igtf`)

## Descripción General
Este módulo implementa la funcionalidad para el manejo del **Impuesto a las Grandes Transacciones Financieras (IGTF)** del 3% en Odoo 17, específicamente adaptado para trabajar en conjunto con el módulo `account_dual_currency` (Doble Moneda).

## Documentación Funcional

### 1. Configuración
Para que el módulo funcione correctamente, se debe configurar un impuesto en el sistema:
1.  Ir a **Contabilidad > Configuración > Impuestos**.
2.  Crear o editar el impuesto correspondiente al IGTF (normalmente 3%).
3.  En la pestaña "Opciones avanzadas" (o pestaña principal dependiendo de la vista), marcar la casilla **"Es IGTF"** (`l10n_ve_is_igtf`).
    *   *Nota: Solo debe haber un impuesto activo marcado con esta opción por compañía.*

### 2. Uso en Facturas de Cliente
Dentro del formulario de factura de cliente (`account.move`), el módulo añade las siguientes características:

#### Sección de Sugerencia IGTF:
En el pie de página de la factura (debajo de los totales), se mostrará una sección informativa con el cálculo sugerido del IGTF.
*   **Si la factura es en USD:** Se muestra la "Base IGTF Sugerido" y "Monto IGTF Sugerido" en Dólares.
*   **Si la factura es en Bs:** Se muestra la "Base IGTF Sugerido (Bs)" y "Monto IGTF Sugerido (Bs)" en Bolívares.
*   El cálculo se basa en la Base Imponible (Subtotal) de la factura, no en el total con IVA.

#### Botón "Aplicar IGTF":
*   Aparece un botón **"Aplicar IGTF"** junto a los montos sugeridos.
*   **Condición:** El botón solo es visible cuando la factura está en estado **Borrador**. Desaparece al confirmar (Publicar) la factura o si el IGTF ya ha sido aplicado.
*   **Acción:** Al hacer clic, el sistema busca el impuesto configurado como "Es IGTF" y lo agrega automáticamente a todas las líneas de factura existentes.

### 3. Reportes
El módulo incluye un reporte PDF específico: **Listado de IGTF Percibido**.
*   **Ubicación:** Menú **Contabilidad > Informes > Listado de IGTF Percibido**.
*   **Wizard:** Permite seleccionar un rango de fechas (`Fecha Inicio` y `Fecha Fin`).
*   **Formato:** Genera un PDF en formato horizontal (Landscape) que lista todas las facturas y notas de crédito donde se aplicó el IGTF.
*   **Datos mostrados:**
    *   Tipo (FACT/NC)
    *   Número de Documento
    *   Fecha
    *   Cliente
    *   Número de Operación (Correlativo en el reporte)
    *   Base IGTF y Monto Percibido (siempre expresados en Bs, convertidos a la tasa del día si la factura fue en USD).

---

## Documentación Técnica

### Estructura del Módulo
*   **Nombre Técnico:** `logicacero_igtf`
*   **Dependencias:** `base`, `account`, `account_dual_currency`.

### Modelos Extendidos

#### `account.tax`
*   Se añade el campo `l10n_ve_is_igtf` (Boolean) para identificar el impuesto IGTF.

#### `account.move`
Se extiende el modelo de facturas para incluir lógica de IGTF y soporte de doble moneda:
*   **Campos:**
    *   `l10n_ve_igtf_applied` (Boolean): Indica si el IGTF ya fue aplicado en este documento.
    *   `igtf_base_suggested` (Monetary): Base imponible sugerida en moneda extranjera (USD).
    *   `igtf_amount_suggested` (Monetary): 3% de la base en moneda extranjera.
    *   `igtf_base_suggested_bs` (Monetary): Base imponible sugerida en moneda local (Bs).
    *   `igtf_amount_suggested_bs` (Monetary): 3% de la base en moneda local.
*   **Métodos:**
    *   `action_apply_igtf_tax()`: Busca el impuesto IGTF y lo añade a `invoice_line_ids`.
    *   `_compute_igtf_suggested()`: Calcula los montos sugeridos. Usa `amount_untaxed_usd` (del módulo `account_dual_currency`) o `amount_untaxed` estándar dependiendo de la moneda del documento para asegurar precisión.

### Reportes (PDF)

#### Wizard: `igtf.report.wizard`
*   Modelo transitorio para capturar el rango de fechas.

#### Abstract Model: `report.logicacero_igtf.report_igtf_template`
*   Lógica de recolección de datos (`_get_report_values`).
*   Realiza búsquedas de facturas (`account.move`) publicadas en el rango de fechas con `l10n_ve_igtf_applied=True`.
*   **Lógica de Conversión:**
    *   Itera sobre las facturas encontradas.
    *   Determina si es FACT o NC (`doc_type`).
    *   Si la factura es en moneda extranjera, convierte el monto IGTF a Bs multiplicando por la tasa de cambio (`tax_today` si existe, o tasa del sistema).

#### Plantilla QWeb: `report_igtf_template`
*   ID Externo: `logicacero_igtf.report_igtf_template`.
*   Renderiza la tabla de transacciones.
*   Usa el formato de papel personalizado `paperformat_igtf_landscape` (A4 Horizontal).

### Vistas
*   **`views/account_move_views.xml`:**
    *   Inyecta el botón y los campos sugeridos en los pies de página de totales.
    *   Maneja la visibilidad condicional para soportar la interfaz de `account_dual_currency` (mostrando campos USD en la columna derecha y campos Bs en la columna izquierda).

### Seguridad
*   Permisos de acceso configurados en `security/ir.model.access.csv` para el wizard de reportes.
