# Guía de Solución: Error de Conciliación Bancaria (Invalid Domain Term)

Esta guía explica el origen y los pasos para corregir el error `ValueError: Invalid domain term ('account_id', 'in', XXX)` que ocurre al abrir o buscar en el widget de conciliación bancaria en Odoo 17.

---

## 1. Diagnóstico del Error

* **Causa**: Odoo 17 genera por defecto dos filtros dinámicos (`receivable_payable_matching` y `misc_matching`) que usan la expresión `('account_id', 'in', tuple(account_ids))`. 
* **El Bug**: Si el diario tiene exactamente **una sola cuenta de pagos pendientes** (ej. ID `522`), `tuple(account_ids)` se convierte en una tupla unitaria `(522,)`. El formateador del cliente web de Odoo (`py_utils.js`) la serializa incorrectamente como `"(522)"` (omitiendo la coma obligatoria en Python).
* **El Fallo**: Al enviarse la petición al servidor, `safe_eval`/`literal_eval` interpreta `(522)` como el entero `522`. El motor SQL falla porque el operador `'in'` requiere una secuencia/lista, no un valor escalar.
* **Filtros Guardados**: Si un usuario guardó un filtro personalizado anteriormente con este error activo (bajo el modelo `ir.filters`), al cargar la vista se disparará el mismo error de forma persistente para ese usuario específico.

---

## 2. Paso 1: Aplicar el Parche de Código (Python)

Debes heredar el modelo `bank.rec.widget` en el módulo de personalización (ej. `account_dual_currency`) y sobrescribir el método `_prepare_embedded_views_data` para convertir los valores de tuplas unitarias a listas estándar (las cuales el cliente web serializa correctamente como arrays JSON sin fallos).

### Código a incorporar en `models/bank_rec_widget.py`:

```python
# -*- coding: utf-8 -*-
import ast
import logging
from odoo import models

_logger = logging.getLogger(__name__)

class BankRecWidget(models.Model):
    _inherit = 'bank.rec.widget'

    def _prepare_embedded_views_data(self):
        res = super()._prepare_embedded_views_data()
        if 'amls' in res and 'dynamic_filters' in res['amls']:
            for filter_data in res['amls']['dynamic_filters']:
                if filter_data.get('domain'):
                    try:
                        # Parsear el dominio stringificado a objetos Python
                        domain = ast.literal_eval(filter_data['domain'])
                        new_domain = []
                        for leaf in domain:
                            # Detectar término ('account_id', 'in', tupla/set)
                            if isinstance(leaf, tuple) and len(leaf) == 3 and leaf[0] == 'account_id' and leaf[1] == 'in':
                                val = leaf[2]
                                if isinstance(val, (tuple, list, set)):
                                    # Convertir a lista para que JS lo formatee como array JSON legítimo
                                    new_domain.append((leaf[0], leaf[1], list(val)))
                                else:
                                    new_domain.append(leaf)
                            else:
                                new_domain.append(leaf)
                        filter_data['domain'] = str(new_domain)
                    except Exception as e:
                        _logger.error("[BANK-RECON-WIDGET] Error al convertir dominio del filtro dinámico: %s", e)
        return res
```

* **Nota**: Una vez subido este cambio, **actualiza el módulo** correspondiente (ej. `account_dual_currency`) desde la interfaz o por línea de comandos para recargar el registro de Odoo.

---

## 3. Paso 2: Limpieza de Filtros Guardados (ir.filters)

Si un usuario en particular sigue experimentando el error tras actualizar el código, se debe a que tiene un filtro personalizado guardado en base de datos con la tupla rota. 

Tienes dos opciones para solucionarlo:

### Opción A: Desde la interfaz de Odoo (Recomendado/Fácil)
1. Pídele al usuario afectado que vaya a **Ajustes > Técnico > Estructura de la Base de Datos > Filtros**.
2. Buscar registros filtrando por:
   * **Modelo**: `account.move.line`
   * **Creado por**: Nombre/ID del usuario afectado.
3. Localizar el filtro con el dominio corrupto (ej. un filtro que contenga `("account_id", "in", (522))`).
4. **Eliminar ese registro de filtro**.
5. El usuario ya podrá ingresar a la conciliación. Posteriormente puede volver a guardar el filtro desde la UI sin problemas (el nuevo código lo guardará correctamente como `[522]`).

### Opción B: Mediante Script de Actualización (Directo en DB)
Si deseas corregirlo directamente sin molestar al usuario, puedes buscar y actualizar el filtro desde la base de datos usando un script XML-RPC o consulta SQL directa:

```python
# Buscar el ID del filtro afectado en ir.filters
filter_record = env['ir.filters'].search([
    ('model_id', '=', 'account.move.line'),
    ('domain', 'like', '("account_id", "in", (522))')
])
if filter_record:
    # Corregir la tupla rota por un array de lista de forma segura
    new_domain = filter_record.domain.replace('(522)', '[522]')
    filter_record.write({'domain': new_domain})
```
