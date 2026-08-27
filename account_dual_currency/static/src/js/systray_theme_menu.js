/* @odoo-module */

import { registry } from "@web/core/registry";
import { Component, onMounted } from "@odoo/owl";

import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

export class CurrencySystrayItem extends Component {

    setup() {
        this.orm = useService("orm");
        onMounted(async () => await this._getCurrencyRateData());
    }

    async _getCurrencyRateData() {
        var self = this;
        var dt = new Date();
        const data = await this.orm.call('res.currency.rate', 'get_systray_dict', [self.id, dt])
        $('.o_exchange_rate').text(data['rate']);
        $('.o_exchange_rate_euro').text(data['rate_euro']);
        $('.currency_rate_date').text(data['date']);
        $('.currency_rate_sell').text(data['sell']);
        $('.currency_rate_buy').text(data['buy']);
    }
}

CurrencySystrayItem.template = "account_dual_currency.SystrayItem";
CurrencySystrayItem.props = {};

export const systrayItem = {
    Component: CurrencySystrayItem,
    isDisplayed: (env) => env.services.user.isSystem,
};

registry.category("systray").add("CurrencySystrayItem", systrayItem, { sequence: 1 });