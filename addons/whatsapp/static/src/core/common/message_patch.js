/** @odoo-module */

import { Message } from "@mail/core/common/message";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

patch(Message.prototype, {
    /** @override */
    get canReplyTo() {
        return super.canReplyTo && !this.message.originThread?.composer?.threadExpired;
    },
    /**
     * @param {MouseEvent} ev
     */
    async onClick(ev) {
        const id = Number(ev.target.dataset.oeId);
        if (ev.target.closest(".o_whatsapp_channel_redirect")) {
            ev.preventDefault();
            let thread = this.store.Thread.get({ model: "discuss.channel", id });
            if (!thread?.hasSelfAsMember) {
                await this.threadService.orm.call("discuss.channel", "add_members", [[id]], {
                    partner_ids: [this.store.user.id],
                });
                thread = this.store.Thread.insert({
                    id,
                    model: "discuss.channel",
                    type: "whatsapp_message",
                });
            }
            this.threadService.open(thread);
            return;
        }
        super.onClick(ev);
    },

    getWhatsappStatusClass() {
        const statusClasses = {
            outgoing: "text-warning",
            sent: "text-success",
            delivered: "text-success",
            read: "text-success",
            received: "text-success",
            error: "text-danger",
            cancel: "text-danger",
        };
        return statusClasses[this.message.whatsappStatus] || "text-muted";
    },

    getWhatsappStatusTitle() {
        const statusTitles = {
            outgoing: _t("The message is being processed."),
            sent: _t("The message has been sent."),
            delivered: _t("The message has been successfully delivered."),
            read: _t("The message has been read by the recipient."),
            received: _t("The message has been successfully received."),
            error: _t("There was an issue sending this message."),
            cancel: _t("The message has been canceled."),
        };
        return statusTitles[this.message.whatsappStatus] || _t("The status of this message is currently unknown.");
    },
});
