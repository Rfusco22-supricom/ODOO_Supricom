/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { Navbar } from "@point_of_sale/app/navbar/navbar";
import { usePos } from "@point_of_sale/app/store/pos_hook";

patch(Navbar.prototype, {
    setup() {
        super.setup();
        this.pos = usePos();
    },

    sendBalance() {
        for (const pm of this.pos.payment_methods) {
            if (pm.use_payment_terminal === "six_iot") {
                pm.payment_terminal.sendBalance();
            }
        }
    },
});
