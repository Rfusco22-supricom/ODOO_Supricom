/** @odoo-module **/

import { FormController } from "@web/views/form/form_controller";
import { useService } from "@web/core/utils/hooks";

export class FormControllerCustomBehavior extends FormController {
    setup() {
        super.setup();
        this.notification = useService("notification");
        this.dialog = useService("dialog");
    }

    /**
     * @override
     */
    async _updateView() {
        await super._updateView(...arguments);
        await this._checkDatesAndDisplayWarning();
    }

    async _checkDatesAndDisplayWarning() {
        const record = this.model.root;
        if (record.data.fiscalyear_lock_date) {
            try {
                const result = await this.model.orm.call(
                    'account.change.lock.date',
                    'check_delivery_orders',
                    [record.data.fiscalyear_lock_date],
                    {}
                );
                
                if (result && result.warning) {
                    // Notificación sticky
                    this.notification.add(result.warning, {
                        title: "ADVERTENCIA IMPORTANTE - SENIAT",
                        type: 'warning',
                        sticky: true,
                    });

                    // Diálogo modal de confirmación
                    this.dialog.add(this.env._t("Advertencia Fiscal"), {
                        body: result.warning,
                        buttons: [
                            {
                                text: this.env._t("Entendido"),
                                close: true,
                                primary: true,
                            }
                        ],
                    });
                }
            } catch (error) {
                console.error("Error checking delivery orders:", error);
                this.notification.add(
                    "Error al verificar órdenes de entrega",
                    {type: 'danger'}
                );
            }
        }
    }
}