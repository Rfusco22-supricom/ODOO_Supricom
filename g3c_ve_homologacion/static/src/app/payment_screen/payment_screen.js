/** @odoo-module **/

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";

patch(PaymentScreen.prototype, {
    async validateOrder(isForceValidate) {
        const order = this.currentOrder;
        const lines = order.get_orderlines();
        const invalidLines = lines.filter(line => {
            const qty = line.get_quantity();
            const price = line.get_unit_price();
            // 1. Cantidad CERO siempre es inválida.
            // 2. Precio CERO o NEGATIVO siempre es inválido.
            // 3. Cantidad NEGATIVA es inválida si NO es un reembolso.
            if (qty === 0 || price <= 0) return true;
            if (qty < 0 && !line.refunded_orderline_id) return true;
            return false;
        });

        if (invalidLines.length > 0) {
            this.popup.add(ErrorPopup, {
                title: _t("Restricción de Homologación"),
                body: _t("No se permiten productos con cantidad cero o negativa en el punto de venta Venezolano."),
            });
            return;
        }
        return super.validateOrder(...arguments);
    },
});
