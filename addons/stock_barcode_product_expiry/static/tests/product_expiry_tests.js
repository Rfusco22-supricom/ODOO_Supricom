/** @odoo-module **/

import { createWebClient, doAction } from "@web/../tests/webclient/helpers";
import { destroy, getFixture, patchDate, patchTimeZone } from "@web/../tests/helpers/utils";

const BARCODE_DATA = {
    data: {
        records: {
            "stock.picking": [
                {
                    id: 1,
                    name: "TEST/IN/0001",
                    move_line_ids: [2],
                    location_id: 5,
                    location_dest_id: 6,
                },
            ],
            "stock.move.line": [
                {
                    id: 2,
                    product_id: 3,
                    product_uom_id: 4,
                    location_id: 5,
                    location_dest_id: 6,
                    expiration_date: "2025-06-15 23:30:00",
                    qty_done: 0,
                    lot_name: "TEST LOT",
                },
            ],
            "product.product": [
                {
                    id: 3,
                    tracking: "lot",
                    display_name: "test barcode",
                    use_expiration_date: true,
                },
            ],
            "uom.uom": [
                {
                    id: 4,
                    name: "Units",
                    category_id: 1,
                    factor: 1.0,
                    rounding: 0.01,
                },
            ],
            "stock.location": [
                {
                    id: 5,
                    barcode: "WH-STOCK",
                    display_name: "WH/STOCK",
                    name: "STOCK",
                    parent_path: "1/7/8",
                },
                {
                    id: 6,
                    barcode: "WH-STOCK",
                    display_name: "WH/STOCK",
                    name: "STOCK",
                    parent_path: "1/7/8",
                },
            ],
            "barcode.nomenclature": [{ id: 1, rule_ids: [] }],
        },
        nomenclature_id: 1,
    },
    groups: { group_uom: true },
};

QUnit.test("expiration date is rendered in user timezone", async (assert) => {
    patchTimeZone(120); // UTC+2
    patchDate(2025, 6, 1, 12, 0, 0); // 2025-07-01 12:00:00
    const webClient = await createWebClient({
        async mockRPC(route, { model, res_id }) {
            if (route === "/stock_barcode/get_barcode_data") {
                return Promise.resolve(BARCODE_DATA);
            }
            if (route === "/web/dataset/call_kw/stock.move/post_barcode_process") {
                return Promise.resolve([]);
            }
        },
    });
    await doAction(webClient, {
        tag: "stock_barcode_client_action",
        type: "ir.actions.client",
        res_model: "stock.picking",
        context: { active_id: 1 },
    });
    const lotEl = getFixture().querySelector(".o_barcode_line div[name=lot]");
    assert.strictEqual(lotEl.textContent.trim(), "TEST LOT (06/16/2025)");
    destroy(webClient);
});
