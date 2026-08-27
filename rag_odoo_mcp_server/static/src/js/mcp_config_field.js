/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useState } from "@odoo/owl";

/**
 * Read-only field widget that renders a (JSON) text value as a monospace code
 * block, preserving every space, indentation level and newline, with a one-click
 * "Copy" button. Used for the generated Claude Desktop / Cursor MCP config block.
 *
 * Self-contained (no dependency on @web/core/copy_button, which does not exist in
 * Odoo 17): the copy is done inline via navigator.clipboard.writeText.
 */
export class McpConfigBlockField extends Component {
    static template = "rag_odoo_mcp_server.McpConfigBlockField";
    static props = { ...standardFieldProps };

    setup() {
        this.state = useState({ copied: false });
    }

    get value() {
        return this.props.record.data[this.props.name] || "";
    }

    async onCopy() {
        try {
            await navigator.clipboard.writeText(this.value);
            this.state.copied = true;
            setTimeout(() => {
                this.state.copied = false;
            }, 1200);
        } catch (e) {
            console.warn("rag_odoo_mcp_server: clipboard copy failed", e);
        }
    }
}

export const mcpConfigBlockField = {
    component: McpConfigBlockField,
    displayName: _t("MCP Config Block"),
    supportedTypes: ["text"],
};

registry.category("fields").add("McpConfigBlock", mcpConfigBlockField);
