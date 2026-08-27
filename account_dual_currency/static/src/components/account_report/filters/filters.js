/** @odoo-module */

import { AccountReport } from "@account_reports/components/account_report/account_report";
import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";
import { patch } from "@web/core/utils/patch";

patch(AccountReportFilters.prototype, {
    setup() {
        super.setup(...arguments);
        console.log(this);
    },
    async appliChangeCurrency(currency) {
        console.log(currency);
        await this.controller.orm.call(
            "account.report",
            "apply_change_curr_conversion",
            [
                this.controller.actionReportId
            ],
            {
                currency_id: currency,
            }
        );

        this.controller.reload('date', this.controller.options);
//        await this.controller.reload('journals', this.controller.options);
    }

});
