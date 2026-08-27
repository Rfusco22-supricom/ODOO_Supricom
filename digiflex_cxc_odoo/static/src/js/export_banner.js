/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";

console.log("[DIGIFLEX CXC] Carga del módulo export_banner.js");

patch(ListController.prototype, {
    setup() {
        super.setup();
        if (this.props && this.props.resModel === "digiflex.cxc.report") {
            window.__digiflex_cxc_controller = this;
            console.log("[DIGIFLEX CXC] ListController registrado para digiflex.cxc.report. Dominio inicial:", this.model?.root?.domain);
        }
    },
});

document.addEventListener("click", async (ev) => {
    const btn = ev.target.closest(".o_btn_export_cxc_excel, button[name='action_export_excel']");
    if (!btn) return;

    ev.preventDefault();
    ev.stopPropagation();

    console.log("[DIGIFLEX CXC] Clic interceptado en botón de exportación:", btn);

    const controller = window.__digiflex_cxc_controller;
    let currentDomain = [];

    if (controller && controller.model && controller.model.root) {
        currentDomain = controller.model.root.domain || [];
        console.log("[DIGIFLEX CXC] Dominio en vivo capturado del ListController:", currentDomain);
    } else {
        console.warn("[DIGIFLEX CXC] Instancia de ListController no encontrada en window.__digiflex_cxc_controller");
    }

    if (controller && controller.actionService) {
        console.log("[DIGIFLEX CXC] Ejecutando acción de servidor mediante controller.actionService...");
        try {
            await controller.actionService.doAction("digiflex_cxc_odoo.action_server_export_cxc_excel", {
                additionalContext: {
                    active_domain: currentDomain,
                },
            });
            console.log("[DIGIFLEX CXC] Acción ejecutada con éxito.");
        } catch (err) {
            console.error("[DIGIFLEX CXC] Error ejecutando acción de servidor:", err);
        }
    } else {
        console.log("[DIGIFLEX CXC] Redirigiendo a ruta HTTP de respaldo /digiflex_cxc_odoo/export_excel");
        window.location.href = "/digiflex_cxc_odoo/export_excel";
    }
}, true);
