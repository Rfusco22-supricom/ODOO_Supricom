# 💰 Distribución Avanzada de Pagos (Multi-Compañía)

## 📋 Descripcións

Módulo avanzado para Odoo 17 que permite la **distribución inteligente y flexible de pagos** en escenarios complejos de contabilidad multi-compañía. Facilita la aplicación parcial de pagos, gestión de pagos de terceros y transferencias inter-compañía de forma automatizada.

### ✨ Características Principales

- ✅ **Aplicación Parcial de Pagos**: Usa solo una parte del saldo disponible de un pago
- 🏢 **Soporte Multi-Compañía**: Gestiona pagos entre diferentes empresas del mismo grupo
- 👥 **Pagos de Terceros**: Aplica pagos de un cliente a facturas de otro cliente
- 🔍 **Búsqueda Global**: Encuentra pagos en todas las compañías y partners
- 📊 **Visualización en Tiempo Real**: Barras de progreso y cálculos automáticos de saldos
- 🔄 **Conciliación Automática**: Genera asientos contables espejo automáticamente
- 💬 **Trazabilidad Completa**: Registra todas las operaciones en el chatter de la factura

---

## 🎯 Casos de Uso

### 1. **Pago Parcial Estándar**
Un cliente paga $500 pero tiene una factura de $300. El sistema permite aplicar solo $300 y dejar $200 disponibles para otras facturas.

### 2. **Pago de Terceros**
El Cliente A paga una factura del Cliente B. El módulo genera automáticamente un asiento de reclasificación de deuda entre ambos clientes.

### 3. **Transferencia Inter-Compañía**
La Compañía A recibe un pago que debe aplicarse a una factura de la Compañía B. El sistema crea asientos espejo en ambas compañías para mantener la contabilidad balanceada.

---

## 📦 Instalación

### Requisitos Previos

- **Odoo 17.0** o superior
- Módulos base: `account`, `web`

### Pasos de Instalación

1. **Clonar o copiar** el módulo en tu directorio de addons:
   ```bash
   cd /path/to/odoo/addons
   git clone <repository-url> account_advanced_dist
   ```

2. **Actualizar lista de aplicaciones**:
   - Ve a `Aplicaciones` → `Actualizar lista de aplicaciones`

3. **Instalar el módulo**:
   - Busca "Distribución Avanzada de Pagos"
   - Haz clic en `Instalar`

---

## 🚀 Uso

### Acceso al Asistente

1. Abre una **factura de cliente o proveedor** (estado: Publicado)
2. Haz clic en el botón **"Asignación Avanzada"** (ubicado en la parte superior)
3. Se abrirá el asistente de distribución de pagos

### Flujo de Trabajo

#### **Paso 1: Seleccionar el Pago**

- **Búsqueda Estándar**: Solo muestra pagos de la misma compañía y partner
- **Búsqueda Global** (toggle): Busca en todas las compañías y partners
  - Usa el campo de búsqueda por referencia para filtrar

#### **Paso 2: Configurar el Monto**

- El sistema muestra:
  - 💵 **Saldo Disponible del Pago**: Cuánto dinero queda sin usar
  - 🔴 **Saldo Pendiente de la Factura**: Cuánto se debe
  - 📊 **Barra de Progreso**: Visualización del uso del pago

- Ingresa el **Monto a Aplicar**:
  - Puede ser parcial o total
  - El sistema valida que no exceda el saldo disponible

#### **Paso 3: Confirmar Operación**

El sistema detecta automáticamente el escenario y ejecuta la lógica correspondiente:

- 🟢 **Estándar**: Conciliación parcial directa
- 🟡 **Terceros**: Genera asiento de reclasificación
- 🔵 **Inter-Compañía**: Crea asientos espejo en ambas compañías

---

## 🏗️ Arquitectura Técnica

### Modelos

#### `account.payment.split.wizard` (TransientModel)

**Campos Principales:**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `invoice_id` | Many2one | Factura destino |
| `payment_id` | Many2one | Pago origen |
| `amount_to_apply` | Monetary | Monto a aplicar |
| `payment_amount_available` | Monetary | Saldo disponible del pago |
| `is_inter_company` | Boolean | Detecta si es inter-compañía |
| `is_third_party_payment` | Boolean | Detecta si es pago de tercero |

**Métodos Principales:**

- `_compute_scenarios()`: Detecta automáticamente el tipo de operación
- `_onchange_payment_id_force_values()`: Calcula el saldo real del pago
- `action_confirm_split()`: Ejecuta la operación según el escenario
- `_process_standard_partial_reconciliation()`: Motor de conciliación estándar
- `_process_third_party_reclassification()`: Motor de reclasificación de terceros
- `_process_inter_company_transfer()`: Motor de transferencias inter-compañía

#### `account.move` (Inherit)

**Métodos Agregados:**

- `action_open_payment_split_wizard()`: Abre el asistente desde la factura

### Vistas

- **`payment_split_wizard_view.xml`**: Formulario del asistente con diseño moderno
- **`account_move_view_inherit.xml`**: Botón de acción en facturas

### Seguridad

- **`ir.model.access.csv`**: Permisos de acceso para el wizard

---

## 🔧 Configuración

### Configuración Multi-Compañía

Para que funcionen las transferencias inter-compañía:

1. **Crear contactos para cada compañía**:
   - Ve a `Contactos` → Crea un contacto para cada empresa
   - Marca como "Es una Compañía"

2. **Asignar contactos a compañías**:
   - Ve a `Configuración` → `Compañías` → Edita cada compañía
   - En el campo "Partner", selecciona el contacto creado

3. **Configurar cuentas contables**:
   - Cada contacto de compañía debe tener:
     - Cuenta por Cobrar (Asset Receivable)
     - Cuenta por Pagar (Liability Payable)

### Diarios Requeridos

El módulo requiere al menos un **Diario General** (tipo: `general`) en cada compañía para generar asientos de reclasificación.

---

## 📊 Ejemplos de Uso

### Ejemplo 1: Pago Parcial Simple

```
Factura: FAC/2024/001 - Cliente A - $1,000 pendiente
Pago: PAY/2024/050 - Cliente A - $1,500 disponible

Acción:
- Aplicar $1,000 a FAC/2024/001
- Quedan $500 disponibles en PAY/2024/050 para otras facturas
```

### Ejemplo 2: Pago de Terceros

```
Factura: FAC/2024/002 - Cliente B - $500 pendiente
Pago: PAY/2024/051 - Cliente A - $500 disponible

Acción:
- Se genera asiento de reclasificación:
  * Débito: Cuenta por Cobrar - Cliente A ($500)
  * Crédito: Cuenta por Cobrar - Cliente B ($500)
- Se concilia automáticamente
```

### Ejemplo 3: Inter-Compañía

```
Factura: FAC/2024/003 - Compañía B - Cliente X - $800
Pago: PAY/2024/052 - Compañía A - Cliente X - $800

Acción:
- Asiento en Compañía A:
  * Débito: Cuenta por Cobrar - Cliente X
  * Crédito: Cuenta por Pagar - Compañía B
  
- Asiento en Compañía B:
  * Débito: Cuenta por Cobrar - Compañía A
  * Crédito: Cuenta por Cobrar - Cliente X
```

---

## 🎨 Recursos Estáticos

### Estructura de Carpetas

```
account_advanced_dist/
├── static/
│   ├── description/          # Imágenes para la tienda de apps
│   │   ├── icon.png         # Icono del módulo (256x256)
│   │   ├── banner.png       # Banner (560x280)
│   │   └── README.md        # Guía de uso
│   └── src/
│       └── img/             # Imágenes para vistas y reportes
│           └── README.md    # Guía de uso
```

### Uso de Imágenes en Vistas

```xml
<!-- En vistas XML -->
<img src="/account_advanced_dist/static/src/img/logo.png" alt="Logo"/>

<!-- En reportes QWeb -->
<img t-att-src="'/account_advanced_dist/static/src/img/logo.png'"/>
```

---

## 🐛 Solución de Problemas

### Error: "No se encontraron líneas conciliables"

**Causa**: El pago o la factura ya están completamente conciliados.

**Solución**: Verifica que ambos documentos estén en estado "Publicado" y tengan saldo pendiente.

### Error: "Fondos Insuficientes"

**Causa**: El monto a aplicar excede el saldo disponible del pago.

**Solución**: Reduce el monto o selecciona otro pago.

### Error: "Falta configurar un Diario General"

**Causa**: No existe un diario de tipo "General" en la compañía.

**Solución**: 
1. Ve a `Contabilidad` → `Configuración` → `Diarios`
2. Crea un nuevo diario de tipo "Miscelánea/General"

### Error: "Faltan cuentas contables en los contactos de las compañías"

**Causa**: Los contactos de las compañías no tienen cuentas por cobrar/pagar configuradas.

**Solución**:
1. Ve al contacto de la compañía
2. Pestaña "Contabilidad"
3. Configura "Cuenta por Cobrar" y "Cuenta por Pagar"

---

## 🔐 Seguridad y Permisos

### Grupos de Acceso

El módulo respeta los permisos estándar de Odoo:

- **Facturación/Contabilidad**: Acceso completo al asistente
- **Usuario**: Sin acceso (solo lectura de facturas)

### Auditoría

Todas las operaciones se registran en:
- 📝 **Chatter de la factura**: Mensaje con detalles de la operación
- 📊 **Asientos contables**: Referencia cruzada en el campo `ref`

---

## 📝 Notas Técnicas

### Cálculo de Saldo Disponible

El módulo calcula el saldo real del pago considerando:

1. Monto original del pago
2. Conciliaciones parciales previas (matched_debit_ids, matched_credit_ids)
3. Corrección de redondeo (< 0.01)

### Manejo de Monedas

- Soporta pagos y facturas en diferentes monedas
- Usa el tipo de cambio de la fecha del pago
- Maneja correctamente `amount_currency` vs `balance`

### Validaciones Automáticas

- ✅ Monto mayor a cero
- ✅ Monto no excede saldo disponible
- ✅ Documentos en estado "Publicado"
- ✅ Existencia de líneas conciliables

---

## 🤝 Contribuciones

Este módulo fue desarrollado por **Lógica Cero** para Odoo 17.

### Reporte de Bugs

Si encuentras un error, por favor reporta:
1. Versión de Odoo
2. Pasos para reproducir
3. Mensaje de error completo
4. Logs del servidor

---

## 📄 Licencia

**OPL-1** (Odoo Proprietary License v1.0)

---

## 📞 Soporte

Para soporte técnico o consultas:
- 📧 Email: soporte@logicacero.com
- 🌐 Web: www.logicacero.com

---

## 🗺️ Roadmap

### Versión 1.1.0 (Planificada)

- [ ] Soporte para múltiples pagos simultáneos
- [ ] Plantillas de distribución automática
- [ ] Reportes de análisis de pagos
- [ ] API REST para integraciones externas

### Versión 1.2.0 (Planificada)

- [ ] Soporte para notas de crédito
- [ ] Distribución proporcional automática
- [ ] Dashboard de pagos pendientes
- [ ] Notificaciones por email

---

## 📚 Recursos Adicionales

### Documentación Relacionada

- [Documentación Oficial de Odoo 17](https://www.odoo.com/documentation/17.0/)
- [Guía de Contabilidad Multi-Compañía](https://www.odoo.com/documentation/17.0/applications/finance/accounting/others/multicurrencies.html)

### Videos Tutoriales

_(Próximamente)_

---

**Última actualización**: Diciembre 2024  
**Versión del módulo**: 17.0.1.0.0
