/** @odoo-module **/

import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { patch } from "@web/core/utils/patch";

patch(ReceiptScreen.prototype, {
    // Deshabilitamos la función de imprimir recibo
    async printReceipt() {
        // No hacemos nada - bloqueamos la impresión de recibos no fiscales
        console.log("Impresión de recibo bloqueada por restricción de homologación");
        return;
    },

    // Deshabilitamos el envío por correo
    async sendReceipt() {
        // No hacemos nada - bloqueamos el envío de recibos no fiscales
        console.log("Envío de recibo bloqueado por restricción de homologación");
        return;
    },
});
