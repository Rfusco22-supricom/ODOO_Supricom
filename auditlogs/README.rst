=========================================
Documentación del Módulo Audit Log (Agromatic)
=========================================

.. contents:: Tabla de Contenidos
   :local:

Introducción
============
El módulo **Audit Log** para Odoo 17 es una solución integral de seguridad y trazabilidad diseñada para **Agromatic**. Su propósito es registrar operaciones críticas, monitorear el acceso y proteger la integridad de los datos mediante un perfil de solo lectura para auditorías externas como las del SENIAT.

**Nota Importante**: Se recomienda encarecidamente instalar este módulo **al final**, después de todos los demás módulos de Odoo. Esto garantiza que las reglas de seguridad y las restricciones de vistas se apliquen correctamente sobre todos los elementos del sistema.

Documentación Funcional
=======================

Características Principales
---------------------------
1.  **Auditoría de Datos Preconfigurada**: El sistema registra operaciones de Crear, Modificar y Eliminar (Write, Create, Unlink) sobre un conjunto de modelos de negocio críticos. **Estas reglas no son configurables por el usuario final**, ya que vienen predefinidas en el código para garantizar una auditoría consistente.
2.  **Registro de Sesiones de Usuario**: Monitorea todos los intentos de inicio de sesión, registrando tanto los accesos exitosos como los fallidos, junto con la dirección IP del usuario.
3.  **Captura de Errores de Cliente**: Registra automáticamente los errores de JavaScript que ocurren en el navegador del usuario, permitiendo al equipo técnico diagnosticar problemas de interfaz de forma proactiva.
4.  **Usuario SENIAT de Solo Lectura**: Crea y configura automáticamente un usuario con las siguientes credenciales:
    *   **Login/Email**: `seniat@gov.ve`
    *   **Contraseña**: `seniat2025`
    Este usuario tiene permisos estrictos de solo lectura sobre los datos de la empresa y no puede acceder a menús de configuración.

Flujo de Trabajo y Operación
----------------------------
1.  **Instalación**: Al instalar el módulo, se ejecutan dos procesos clave:
    *   Se crean las **reglas de auditoría** predefinidas en estado "suscrito".
    *   Se crea y configura el **usuario SENIAT** con sus restricciones de acceso.
2.  **Activación de Reglas**: Un administrador del sistema debe navegar al menú técnico de Reglas de Auditoría y **activar** las reglas que desee monitorear. Mientras una regla no esté activa, no se registrarán logs para ese modelo.
3.  **Operación Diaria**: Los usuarios trabajan de forma normal. El sistema, en segundo plano, registra las acciones sobre los modelos cuyas reglas están activas.
4.  **Monitoreo y Auditoría**: Los administradores pueden consultar los diferentes apartados del menú "Audit Log" para revisar cambios en los datos, sesiones o errores de cliente.

Modelos Auditados (Predefinidos en el código)
---------------------------------------------
El módulo incluye reglas de auditoría listas para ser activadas para los siguientes modelos:

*   **Contabilidad**: `account.move`, `account.move.line`, `account.account`, `account.journal`
*   **Ventas**: `sale.order`
*   **Compras**: `purchase.order`
*   **Inventario**: `stock.picking`, `stock.move`
*   **Base del Sistema**: `res.partner`, `res.users`

Modelos con Acceso Restringido para SENIAT (Solo Lectura)
---------------------------------------------------------
El perfil "SENIAT" tiene permisos de **solo lectura** sobre un conjunto extendido de modelos para garantizar la integridad de los datos durante la consulta. La siguiente lista detalla los modelos cubiertos por estas restricciones:

*   **Contabilidad**:
    *   `account.move` (Asientos Contables)
    *   `account.move.line` (Líneas de Asientos)
    *   `account.payment` (Pagos)
    *   `account.journal` (Diarios)
    *   `account.account` (Plan de Cuentas)
    *   `account.analytic.distribution.model` (Modelos de Distribución Analítica)
    *   `account.analytic.account` (Cuentas Analíticas)
    *   `account.analytic.plan` (Planes Analíticos)
*   **Ventas**:
    *   `sale.order` (Órdenes de Venta)
    *   `sale.order.line` (Líneas de Venta)
*   **Compras**:
    *   `purchase.order` (Órdenes de Compra)
    *   `purchase.order.line` (Líneas de Compra)
*   **Inventario**:
    *   `stock.picking` (Transferencias)
    *   `stock.move` (Movimientos de Stock)
    *   `stock.quant` (Cantidades de Stock)
    *   `product.product` (Productos)
    *   `product.template` (Plantillas de Producto)
*   **Sistema y Base**:
    *   `res.users` (Usuarios)
    *   `res.company` (Compañías)
    *   `res.partner` (Contactos)
    *   `res.currency` (Monedas)
    *   `res.currency.rate` (Tasas de Cambio)
*   **Auditoría (el propio módulo)**:
    *   `auditlog.log`, `auditlog.log.line`, `auditlog.rule`, `auditlog.http.session`, `auditlog.http.request`

Documentación Técnica
=====================

Estructura y Componentes Clave
------------------------------
*   **Modelos**:
    *   `auditlog.rule`: Almacena las reglas de auditoría. Se cargan desde `data/auditlog_rules_data.xml` y el menú para editarlas (`auditlog_view.xml`) está oculto para los usuarios.
    *   `auditlog.log` y `auditlog.log.line`: Guardan los registros de cambios (quién, cuándo, qué, valor anterior y valor nuevo).
    *   `auditlog.http.session`: Registra los intentos de inicio de sesión (sobrescribe el método `_login` de `res.users`).
    *   `auditlog.client.error`: Almacena los errores de JavaScript.
*   **Hook de Post-Instalación (`hooks.py`)**:
    *   El hook `post_init_setup_seniat_user` es fundamental. Realiza las siguientes acciones:
        1.  Crea el usuario `seniat` con login `seniat@gov.ve` y contraseña `seniat2025` si no existe.
        2.  Lo asigna al grupo de solo lectura `auditlogs.group_seniat_readonly`.
        3.  Lo establece como "Usuario Interno".
        4.  **Oculta menús críticos**: Modifica directamente los registros de `ir.ui.menu` para que los menús de configuración de Contabilidad, Ventas, Compras, Inventario y Ajustes (Técnico y General) solo sean visibles para grupos de administradores, excluyendo explícitamente al usuario SENIAT.
*   **Reglas de Seguridad (`security/ir_rule_seniat.xml`)**:
    *   Contiene las `ir.rule` (Reglas de Registro) que impiden a nivel de base de datos las operaciones de escritura, creación y borrado (`perm_write="0"`, `perm_create="0"`, `perm_unlink="0"`) para el grupo del SENIAT en más de 40 modelos.
*   **JavaScript (`static/src/js/client_error_handler.js`)**:
    *   Implementa un manejador de errores global que captura excepciones no controladas, las almacena en `localStorage` y las envía al backend de Odoo.

Guía de Pruebas y Validación
============================

1. Captura de Errores de Cliente
--------------------------------
**Prueba:**
1.  Inicie sesión en Odoo.
2.  Abra la consola del navegador (F12 > Pestaña "Consola").
3.  Ejecute el comando: `setTimeout(() => { throw new Error("Prueba de Error Forzado para Agromatic"); }, 1000);`
4.  Navegue a **Audit Log > Client Errors**.
5.  Verifique que se ha creado un nuevo registro con el mensaje "Prueba de Error Forzado para Agromatic".

2. Inicio de Sesión Fallido
---------------------------
**Prueba:**
1.  Cierre la sesión o abra una ventana de incógnito.
2.  En la página de login, intente acceder con el usuario `seniat@gov.ve` pero una **contraseña incorrecta**.
3.  Ingrese correctamente con su usuario administrador.
4.  Vaya a **Audit Log > Sessions**.
5.  Confirme que existe un registro con estado **"failed"** para el intento fallido.

3. Verificación del Usuario SENIAT y sus Restricciones
------------------------------------------------------
**Prueba:**
1.  Como administrador, vaya a **Ajustes > Usuarios y Compañías > Usuarios** y verifique que el usuario con login `seniat@gov.ve` existe y pertenece al grupo `SENIAT Readonly Group`.
2.  Cierre sesión e inicie sesión con el usuario `seniat@gov.ve` y la contraseña `seniat2025`.
3.  **Verificación de menús**: Confirme que los menús de "Configuración" en los módulos de Contabilidad, Ventas, Compras e Inventario no son visibles. Tampoco debe ver el menú "Técnico" en Ajustes.
4.  **Verificación de solo lectura**:
    *   Vaya a "Contactos" e intente **crear** o **editar** un contacto. Los botones de "Guardar" y "Crear" no deberían estar disponibles o deberían fallar al usarse.
    *   Repita el proceso para una factura o un pedido de venta.

4. Prueba de Auditoría de Datos
-------------------------------
**Prueba:**
1.  Vaya a la aplicación de **Contactos**.
2.  Cree un nuevo contacto llamado "Cliente de Prueba Agromatic".
3.  Edite ese mismo contacto y cambie su nombre a "Cliente de Prueba Modificado".
4.  Vuelva a la aplicación **Audit Log > Logs**.
5.  Filtre por el modelo `res.partner`. Debería ver dos registros:
    *   Un log de tipo `create`.
    *   Un log de tipo `write` que en sus líneas de detalle muestra el cambio del nombre.
