# Guía de Solución: Nóminas y Corrección de Plazos de Pago / Facturas en Producción

Este documento detalla los pasos para aplicar en producción:
1. La corrección de los cálculos de la nómina (días, horas y horario laboral).
2. La corrección de las fechas de vencimiento de facturas afectadas.
3. La eliminación de la línea "Término de Pago" en los PDFs de las facturas.

---

## 1. Diagnóstico de los Errores

### A. Recibo de Nómina
* **Horario Laboral (40h vs 44h):** Los calendarios de 44 horas semanales carecían de turnos en sábados (calculando 40h).
* **Días y Horas en la Quincena:** Calculaba 10 días y 80 horas por las entradas de trabajo del 1 al 15, en vez de los **15 días** y **88 horas** legales.
* **Etiqueta "Medio día" incorrecta:** Odoo promediaba 5.86 horas diarias (88 horas / 15 días). Al ser menor a las 8.0 horas diarias estándar del calendario, consideraba la jornada como reducida e inyectaba el sufijo " (Medio día)" en la descripción de la asistencia.
* **Unificación del Décimo Tercer Mes en Quincena:** Incluir el Décimo Tercer Mes en la nómina quincenal regular generaba riesgos de retención incorrecta. El D3M está exento de Seguro Educativo y Riesgos Profesionales, y tiene tasas específicas (7.25% empleado, 10.75% patronal), a diferencia de las tasas regulares de la quincena (9.75% de empleado y 12.25% + riesgos de patronal).

### B. Fechas de Vencimiento y Plazos de Pago en Facturas
* **Discrepancia en vencimientos (Caso Zenvo 5036376):** Facturas creadas antes del 30 de junio quedaron con fecha de vencimiento a 45 días porque el plazo de pago ID 19 (`21 días (copia)`) fue modificado en base de datos.
* **Plazos de pago alterados:** Plazos de pago del sistema fueron editados manualmente en sus líneas (ej: "30 Days" calculaba 90 días, "45 días (copia)" calculaba 60 días), lo que alteró los cálculos de vencimiento de los clientes que los tenían asociados.
* **Línea de "Término de Pago" en PDFs:** Se requería eliminar por completo el texto/comentario de plazos de pago en el pie/cabecera de las facturas impresas.

---

## 2. Paso 1: Scripts de Base de Datos a Ejecutar (Producción)

### A. Corregir Calendarios de Nómina (44 horas)
Ejecutar el script Python para agregar el turno del sábado por la mañana:
```python
import xmlrpc.client

URL = 'URL_PRODUCCION'
DB = 'DB_PRODUCCION'
USER = 'admin'
PASSWORD = 'PASSWORD_PRODUCCION'

common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
uid = common.authenticate(DB, USER, PASSWORD, {})
models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')

# Buscar calendarios con '44' en su nombre
cal_ids = models.execute_kw(
    DB, uid, PASSWORD,
    'resource.calendar', 'search',
    [[('name', 'ilike', '44')]]
)

for cal_id in cal_ids:
    cal_data = models.execute_kw(
        DB, uid, PASSWORD,
        'resource.calendar', 'read',
        [cal_id],
        {'fields': ['name', 'hours_per_week']}
    )[0]
    
    # Si sigue calculando 40.0 horas, agregar el sábado mañana (4 horas)
    if cal_data['hours_per_week'] < 44.0:
        print(f"Corrigiendo calendario: {cal_data['name']}")
        models.execute_kw(
            DB, uid, PASSWORD,
            'resource.calendar.attendance', 'create',
            [{
                'name': 'Sábado por la mañana',
                'dayofweek': '5',  # Sábado (Lunes=0, Sábado=5)
                'hour_from': 8.0,
                'hour_to': 12.0,
                'day_period': 'morning',
                'calendar_id': cal_id,
            }]
        )
```

### B. Corregir Fechas de Vencimiento en Facturas Afectadas
Ejecutar el script Python **[fix_prod_due_dates.py](file:///home/aecas/Documentos/DIGIFLEX/supricom/scratch/fix_prod_due_dates.py)** para recalcular a 30 días la fecha de vencimiento y el apunte por cobrar de las facturas de producción afectadas:
```python
import xmlrpc.client
from datetime import datetime, timedelta

URL = 'URL_PRODUCCION'
DB = 'DB_PRODUCCION'
USER = 'admin'
PASSWORD = 'PASSWORD_PRODUCCION'

common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
uid = common.authenticate(DB, USER, PASSWORD, {})
models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')

context = {'allowed_company_ids': [9], 'company_id': 9, 'check_move_validity': False}

# IDs de facturas específicas a corregir
target_ids = [155155, 155143, 154741, 154291, 154051, 153779, 152905, 150912, 150803, 150222, 149609]

moves = models.execute_kw(
    DB, uid, PASSWORD,
    'account.move', 'read',
    [target_ids],
    {
        'fields': ['id', 'name', 'invoice_date', 'invoice_date_due', 'invoice_payment_term_id', 'partner_id'],
        'context': context
    }
)

print(f"Actualizando {len(moves)} facturas...")
for m in moves:
    move_id = m['id']
    inv_date = datetime.strptime(m['invoice_date'], '%Y-%m-%d').date()
    new_due_date = (inv_date + timedelta(days=30)).strftime('%Y-%m-%d')
    
    # 1. Actualizar account.move
    models.execute_kw(
        DB, uid, PASSWORD,
        'account.move', 'write',
        [[move_id], {'invoice_date_due': new_due_date}],
        {'context': context}
    )
    
    # 2. Actualizar apunte por cobrar (account.move.line)
    line_ids = models.execute_kw(
        DB, uid, PASSWORD,
        'account.move.line', 'search',
        [[('move_id', '=', move_id), ('account_id.account_type', '=', 'asset_receivable')]],
        {'context': context}
    )
    if line_ids:
        models.execute_kw(
            DB, uid, PASSWORD,
            'account.move.line', 'write',
            [line_ids, {'date_maturity': new_due_date}],
            {'context': context}
        )
```

---

## 3. Paso 2: Desplegar y Actualizar Código en Producción

### 1. Integración en Git
Asegurarse de fusionar y subir los cambios de la rama `QA` a la rama de `Producción`. Los archivos modificados en este despliegue son:

* **Nóminas (Módulo `fix_payroll_code` en versión `17.0.1.2.0`):**
  * [hr_payslip.py](file:///home/aecas/Documentos/DIGIFLEX/supricom/fix_payroll_code/models/hr_payslip.py) -> Sobrescribe `compute_sheet()` para refrescar worked days automáticamente y `_is_half_day()` en `hr.payslip.worked_days` para corregir la etiqueta de medio día.
  * [post-migrate_payroll.py](file:///home/aecas/Documentos/DIGIFLEX/supricom/fix_payroll_code/migrations/17.0.1.2.0/post-migrate_payroll.py) -> Script de migración automática que al actualizar el módulo en base de datos:
    1. Desactiva la regla `DTM` de la estructura quincenal regular.
    2. Corrige la tasa del Seguro Educativo (`SE`) al 1.25% en la quincena regular.
    3. Crea la estructura especial `"Décimo Tercer Mes"` y sus reglas salariales (`DTM` al 8.33%, `SS_DTM` deducción empleado al 7.25%, `SS_Patronal_DTM` aporte patronal al 10.75% y `NET` sin Seguro Educativo ni Riesgos Profesionales).
* **Eliminación de "Término de Pago" y Paginación (Máx 20 items) en Reportes PDF de Forma Libre:**
  * [invoice_template.xml](file:///home/aecas/Documentos/DIGIFLEX/supricom/forma_libre/report/invoice_template.xml) (Módulo `forma_libre`)
  * [invoice_template_dual.xml](file:///home/aecas/Documentos/DIGIFLEX/supricom/forma_libre/report/invoice_template_dual.xml) (Módulo `forma_libre`)
  * [invoice_template.xml](file:///home/aecas/Documentos/DIGIFLEX/supricom/supricom_forma_libre_igtf/report/invoice_template.xml) (Módulo `supricom_forma_libre_igtf`)
  * [invoice_template_dual.xml](file:///home/aecas/Documentos/DIGIFLEX/supricom/supricom_forma_libre_igtf/report/invoice_template_dual.xml) (Módulo `supricom_forma_libre_igtf`)
  * [invoice_templates.xml](file:///home/aecas/Documentos/DIGIFLEX/supricom/multipac_felpa/views/invoice_templates/invoice_templates.xml) (Módulo `multipac_felpa`)
  * [report_invoice.xml](file:///home/aecas/Documentos/DIGIFLEX/supricom/multipac_felpa/views/invoice_templates/report_invoice.xml) (Módulo `multipac_felpa` - Sobrescribe la plantilla nativa)

### 2. Actualizar Módulos en Odoo
Una vez que el código esté en producción, actualizar los siguientes módulos desde la interfaz o vía XML-RPC:
```python
# Script para actualizar módulos vía XML-RPC
modules = ['fix_payroll_code', 'forma_libre', 'supricom_forma_libre_igtf', 'multipac_felpa']
for mod in modules:
    ids = models.execute_kw(DB, uid, PASSWORD, 'ir.module.module', 'search', [[('name', '=', mod)]])
    if ids:
        print(f"Actualizando {mod}...")
        models.execute_kw(DB, uid, PASSWORD, 'ir.module.module', 'button_immediate_upgrade', [ids])
```

---

## 4. Paso 3: Verificación y Recálculo de Recibos
Para aplicar la corrección a los recibos de nómina quincenales en estado Borrador/Espera (*Draft* / *Verify*), el sistema ahora lo hace automáticamente cuando se calcula la hoja (gracias a la sobrescritura de `compute_sheet`):
1. Ingresar al lote de nóminas de producción o al recibo del empleado afectado.
2. Hacer clic directamente en **"Calcular Hoja"** (o llamar a `compute_sheet`).
3. Verificar en la nómina quincenal regular que:
   * **Horario laboral:** `44.0` (obtenido del contrato).
   * **Días de asistencia:** `15.0` días.
   * **Horas de asistencia:** `88.0` horas (u `80.0` horas para contratos de 40h semanales).
   * **Descripción de la Asistencia:** Debe figurar como `"Asistencia"` o `"Attendance"` y **NO** contener el sufijo `" (Medio día)"`.
   * **Seguro Educativo:** Deducción calculada en **1.25%** (`0.0125`) para el empleado (en lugar del 1.50% anterior).
   * **Riesgo Profesional:** **No debe figurar** en el recibo de salario impreso del empleado.
   * **Décimo Tercer Mes:** **No debe calcularse** dentro de la planilla regular (la regla DTM debe aparecer como inactiva/no listada).

4. **Verificación de la Nómina Especial de Décimo Tercer Mes**:
   * Confirmar que existe la estructura salarial **"Décimo Tercer Mes"**.
   * Crear un recibo o lote de nóminas de prueba asignándole esta estructura y verificar que:
     * Se calcule la asignación **Décimo Tercer Mes (DTM)** (8.33% de los acumulados cuatrimestrales).
     * Se aplique la deducción del colaborador de **Seguro Social DTM (SS_DTM)** con la tasa especial de **7.25%**.
     * Se calcule el aporte patronal de **Seguro Social Patronal DTM (SS_Patronal_DTM)** con la tasa especial de **10.75%**.
     * No se calculen deducciones de Seguro Educativo ni de Riesgos Profesionales.

