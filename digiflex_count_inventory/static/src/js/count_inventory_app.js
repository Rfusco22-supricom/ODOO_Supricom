/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class CountInventoryApp extends Component {
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");

        const todayDate = new Date().toISOString().split("T")[0];
        const yesterdayDate = new Date(Date.now() - 86400000).toISOString().split("T")[0];
        this.autosaveTimer = null;

        this.state = useState({
            step: 1, // 1: Setup/Select, 2: Employee PIN, 3: Count Workspace
            locations: [],
            employees: [],
            activeSessions: [],
            isManager: false,
            autosaveStatus: "saved", // "saved", "saving"
            productFilterMode: "my_items", // "my_items" | "all_items"
            massAssignText: "",
            massAssignEmpId: "",
            newSession: {
                location_id: "",
                count_type: "daily",
                date: todayDate,
                sales_target_date: yesterdayDate,
                hide_theoretical_qty: false,
                selectedEmployeeIds: [],
            },
            selectedEmployee: null,
            pin: "",
            pinError: false,
            currentSession: null,
            searchQuery: "",
        });

        onWillStart(async () => {
            await this.loadInitialData();
        });
    }

    async loadInitialData() {
        try {
            const data = await this.orm.call("digiflex.count.inventory", "get_initial_data", []);
            this.state.locations = data.locations || [];
            this.state.employees = data.employees || [];
            this.state.isManager = Boolean(data.is_manager);

            const serverSessions = data.activeSessions || data.active_sessions || [];
            const sessionMap = new Map();

            // Insertar primero las sesiones creadas localmente
            for (const s of this.state.activeSessions) {
                if (s && s.id) {
                    sessionMap.set(s.id, s);
                }
            }
            // Fusionar/actualizar con las del servidor
            for (const s of serverSessions) {
                if (s && s.id) {
                    sessionMap.set(s.id, s);
                }
            }

            const mergedList = Array.from(sessionMap.values()).sort((a, b) => b.id - a.id);
            this.state.activeSessions.splice(0, this.state.activeSessions.length, ...mergedList);

            if (this.state.locations.length > 0 && !this.state.newSession.location_id) {
                this.state.newSession.location_id = this.state.locations[0].id;
            }
        } catch (error) {
            console.error("Error al cargar datos iniciales:", error);
            this.notification.add("Error al conectar con el servidor", { type: "danger" });
        }
    }

    toggleEmployeeAssignment(empId) {
        const index = this.state.newSession.selectedEmployeeIds.indexOf(empId);
        if (index > -1) {
            this.state.newSession.selectedEmployeeIds.splice(index, 1);
        } else {
            this.state.newSession.selectedEmployeeIds.push(empId);
        }
    }

    async startNewSession() {
        if (!this.state.newSession.location_id) {
            this.notification.add("Por favor seleccione una ubicación.", { type: "warning" });
            return;
        }

        try {
            const sessionData = await this.orm.call(
                "digiflex.count.inventory",
                "create_session_from_owl",
                [
                    parseInt(this.state.newSession.location_id),
                    this.state.newSession.count_type,
                    this.state.newSession.hide_theoretical_qty,
                    this.state.newSession.selectedEmployeeIds,
                    this.state.newSession.date,
                    this.state.newSession.sales_target_date
                ]
            );

            const newCard = {
                id: sessionData.id,
                name: sessionData.name,
                date: sessionData.date,
                sales_target_date: sessionData.sales_target_date,
                location_id: sessionData.location_id,
                location_name: sessionData.location_name,
                count_type: sessionData.count_type,
                hide_theoretical_qty: sessionData.hide_theoretical_qty,
                state: sessionData.state,
                total_items: sessionData.total_items,
                total_differences: sessionData.total_differences,
                employees: sessionData.employees || [],
            };

            const exists = this.state.activeSessions.some(s => s.id === newCard.id);
            if (!exists) {
                this.state.activeSessions.unshift(newCard);
            }

            this.notification.add("¡Sesión agendada exitosamente! Actividades notificadas y productos distribuidos entre los operadores.", { type: "success" });
            this.state.newSession.selectedEmployeeIds = [];
            
            // Si es manager, abrir directamente la sesión en Paso 3
            if (this.state.isManager) {
                await this.openExistingSession(sessionData.id);
            } else {
                this.state.step = 1;
                await this.loadInitialData();
            }
        } catch (error) {
            console.error(error);
            this.notification.add(error.message || "Error al agendar la sesión de conteo.", { type: "danger" });
        }
    }

    async openExistingSession(sessionId) {
        try {
            const sessionData = await this.orm.call(
                "digiflex.count.inventory",
                "get_session_details",
                [sessionId]
            );
            this.state.currentSession = sessionData;

            if (this.state.isManager) {
                // El administrador ingresa directamente a la mesa de trabajo (Paso 3) para gestionar y asignar sin pedir PIN
                this.state.selectedEmployee = null;
                this.state.productFilterMode = "all_items";
                this.state.step = 3;
            } else {
                // El operador debe seleccionar su usuario y autenticarse con su PIN en el Paso 2
                this.state.step = 2;
            }
        } catch (error) {
            console.error(error);
            this.notification.add("Error al abrir la sesión seleccionada.", { type: "danger" });
        }
    }

    selectEmployee(employee) {
        this.state.selectedEmployee = employee;
        this.state.pin = "";
        this.state.pinError = false;
    }

    appendPin(num) {
        if (this.state.pin.length < 4) {
            this.state.pin += num;
        }
    }

    clearPin() {
        this.state.pin = "";
        this.state.pinError = false;
    }

    async verifyPin() {
        const emp = this.state.selectedEmployee;
        if (!emp) return;

        try {
            const isValid = await this.orm.call(
                "digiflex.count.inventory",
                "verify_employee_pin",
                [emp.id, this.state.pin]
            );

            if (isValid) {
                if (this.state.currentSession && !this.state.currentSession.employees.some(e => e.id === emp.id)) {
                    this.state.currentSession.employees.push({ id: emp.id, name: emp.name });
                }
                this.state.step = 3;
                this.state.productFilterMode = "my_items";
                this.notification.add(`Bienvenido ${emp.name}`, { type: "success" });
            } else {
                this.state.pinError = true;
                this.state.pin = "";
                this.notification.add("PIN / NIP incorrecto. Intente de nuevo.", { type: "danger" });
            }
        } catch (error) {
            console.error("Error al verificar PIN:", error);
            this.notification.add("Error al validar PIN en el servidor.", { type: "danger" });
        }
    }

    goBack() {
        if (this.state.step === 3) {
            if (this.state.isManager) {
                this.state.step = 1;
                this.state.currentSession = null;
            } else {
                this.state.step = 2;
                this.state.pin = "";
                this.state.selectedEmployee = null;
            }
        } else if (this.state.step === 2) {
            if (this.state.selectedEmployee) {
                this.state.selectedEmployee = null;
                this.state.pin = "";
            } else {
                this.state.step = 1;
                this.state.currentSession = null;
            }
        }
    }

    exitApp() {
        if (window.history.length > 1) {
            window.history.back();
        } else {
            this.action.doAction({
                type: "ir.actions.act_url",
                url: "/web",
                target: "self",
            });
        }
    }

    setFilterMode(mode) {
        this.state.productFilterMode = mode;
    }

    async applyMassAssignmentOWL() {
        if (!this.state.currentSession || !this.state.currentSession.lines) return;
        if (!this.state.massAssignEmpId) {
            this.notification.add("Por favor seleccione un operador para asignar.", { type: "warning" });
            return;
        }

        const empId = parseInt(this.state.massAssignEmpId);
        const filterText = (this.state.massAssignText || "").toLowerCase().trim();
        const empObj = this.state.employees.find(e => e.id === empId);

        let count = 0;
        for (const line of this.state.currentSession.lines) {
            if (!filterText || line.product_name.toLowerCase().includes(filterText) || line.default_code.toLowerCase().includes(filterText) || line.barcode.toLowerCase().includes(filterText)) {
                line.assigned_employee_id = empId;
                line.assigned_employee_name = empObj ? empObj.name : "";
                line._dirty = true;
                count++;
            }
        }

        if (count === 0) {
            this.notification.add("No se encontraron productos que coincidan con el filtro introducido.", { type: "warning" });
            return;
        }

        this.notification.add(`Se asignaron ${count} productos a ${empObj ? empObj.name : 'operador'} exitosamente.`, { type: "success" });
        await this.performAutosave();
    }

    get myAssignedLinesCount() {
        if (!this.state.currentSession || !this.state.currentSession.lines || !this.state.selectedEmployee) return 0;
        const empId = parseInt(this.state.selectedEmployee.id);
        return this.state.currentSession.lines.filter(l => l.assigned_employee_id && parseInt(l.assigned_employee_id) === empId).length;
    }

    get filteredLines() {
        if (!this.state.currentSession || !this.state.currentSession.lines) return [];

        let lines = this.state.currentSession.lines;

        if (this.state.productFilterMode === "my_items" && this.state.selectedEmployee) {
            const empId = parseInt(this.state.selectedEmployee.id);
            lines = lines.filter(l => l.assigned_employee_id && parseInt(l.assigned_employee_id) === empId);
        }

        const query = this.state.searchQuery.toLowerCase().trim();
        if (!query) return lines;

        return lines.filter(l =>
            l.product_name.toLowerCase().includes(query) ||
            l.default_code.toLowerCase().includes(query) ||
            l.barcode.toLowerCase().includes(query)
        );
    }

    get totalLinesCount() {
        return this.state.currentSession && this.state.currentSession.lines ? this.state.currentSession.lines.length : 0;
    }

    get itemsCountedCount() {
        if (!this.state.currentSession || !this.state.currentSession.lines) return 0;
        return this.state.currentSession.lines.filter(l => l.is_counted).length;
    }

    get progressPercentage() {
        const total = this.totalLinesCount;
        if (total === 0) return 0;
        return Math.min(100, Math.round((this.itemsCountedCount / total) * 100));
    }

    get totalDifferencesCount() {
        if (!this.state.currentSession || !this.state.currentSession.lines) return 0;
        return this.state.currentSession.lines.filter(l => Math.abs(l.difference_qty) > 0.0001).length;
    }

    changeQty(line, delta) {
        line.counted_qty = Math.max(0, line.counted_qty + delta);
        line.is_counted = true;
        line._dirty = true;
        this.recomputeLineDifference(line);
        this.triggerAutosave();
    }

    onInputQty(line, ev) {
        const val = parseFloat(ev.target.value) || 0.0;
        line.counted_qty = Math.max(0, val);
        line.is_counted = true;
        line._dirty = true;
        this.recomputeLineDifference(line);
        this.triggerAutosave();
    }

    onInputNote(line, ev) {
        line.notes = ev.target.value;
        line._dirty = true;
        this.triggerAutosave();
    }

    onAssignOperator(line, ev) {
        const empId = parseInt(ev.target.value) || false;
        line.assigned_employee_id = empId;
        const empObj = this.state.employees.find(e => e.id === empId);
        line.assigned_employee_name = empObj ? empObj.name : "";
        line._dirty = true;
        this.triggerAutosave();
    }

    recomputeLineDifference(line) {
        const diff = line.counted_qty - line.theoretical_qty;
        line.difference_qty = diff;
        if (Math.abs(diff) < 0.0001) {
            line.difference_state = 'match';
        } else if (diff < 0) {
            line.difference_state = 'missing';
        } else {
            line.difference_state = 'surplus';
        }
    }

    triggerAutosave() {
        this.state.autosaveStatus = "saving";
        if (this.autosaveTimer) {
            clearTimeout(this.autosaveTimer);
        }
        this.autosaveTimer = setTimeout(async () => {
            await this.performAutosave();
        }, 800);
    }

    async performAutosave() {
        if (!this.state.currentSession || !this.state.currentSession.lines) return;
        const dirtyLines = this.state.currentSession.lines.filter(l => l._dirty);
        if (dirtyLines.length === 0) {
            this.state.autosaveStatus = "saved";
            return;
        }
        try {
            const linesData = dirtyLines.map(l => ({
                id: l.id,
                counted_qty: l.counted_qty,
                is_counted: Boolean(l.is_counted),
                assigned_employee_id: l.assigned_employee_id,
                notes: l.notes
            }));

            await this.orm.call(
                "digiflex.count.inventory",
                "save_session_lines_owl",
                [this.state.currentSession.id, linesData]
            );
            for (const l of dirtyLines) {
                l._dirty = false;
            }
            this.state.autosaveStatus = "saved";
        } catch (error) {
            console.error("Error en autoguardado:", error);
            this.state.autosaveStatus = "saved";
        }
    }

    async saveDraft() {
        if (!this.state.currentSession) return;
        if (this.autosaveTimer) {
            clearTimeout(this.autosaveTimer);
        }
        await this.performAutosave();
        this.notification.add("Borrador guardado exitosamente.", { type: "info" });
    }

    async printPdfReport() {
        if (!this.state.currentSession) return;
        await this.saveDraft();
        this.action.doAction({
            type: "ir.actions.report",
            report_name: "digiflex_count_inventory.report_count_inventory",
            report_type: "qweb-pdf",
            model: "digiflex.count.inventory",
            res_ids: [this.state.currentSession.id],
            context: {
                active_ids: [this.state.currentSession.id],
                active_id: this.state.currentSession.id,
            },
        });
    }

    async createOdooAdjustment() {
        if (!this.state.currentSession) return;
        await this.saveDraft();
        try {
            await this.orm.call(
                "digiflex.count.inventory",
                "action_create_stock_quant_adjustment",
                [this.state.currentSession.id]
            );
            this.state.currentSession.adjustment_applied = true;
            this.notification.add("Resumen de diferencias de conteo registrado exitosamente en el Chatter.", { type: "success" });
        } catch (error) {
            console.error(error);
            this.notification.add(error.message || "Error al crear ajuste en Odoo.", { type: "danger" });
        }
    }

    async finishOperatorCount() {
        if (!this.state.currentSession) return;
        await this.saveDraft();
        try {
            const empId = this.state.selectedEmployee ? this.state.selectedEmployee.id : false;
            const res = await this.orm.call(
                "digiflex.count.inventory",
                "action_finish_operator_count",
                [this.state.currentSession.id],
                { employee_id: empId }
            );

            if (res && res.all_counted) {
                this.notification.add("¡Excelente! Se completó el 100% del conteo. La sesión fue cerrada automáticamente.", { type: "success" });
            } else {
                this.notification.add(`Has finalizado el conteo de tus productos. Quedan ${res.remaining_uncounted} productos pendientes por contar en la sesión.`, { type: "info" });
            }
            this.state.step = 1;
            this.state.currentSession = null;
            await this.loadInitialData();
        } catch (error) {
            console.error(error);
            this.notification.add(error.message || "Error al finalizar el conteo.", { type: "danger" });
        }
    }

    async closeSessionDayManager() {
        if (!this.state.currentSession) return;
        if (!confirm("¿Está seguro de realizar el cierre general de la sesión? La sesión cambiará a estado cerrado.")) return;

        await this.saveDraft();
        try {
            await this.orm.call(
                "digiflex.count.inventory",
                "action_close",
                [this.state.currentSession.id]
            );
            this.notification.add("Cierre general de sesión registrado exitosamente.", { type: "success" });
            await this.printPdfReport();
            this.state.step = 1;
            this.state.currentSession = null;
            await this.loadInitialData();
        } catch (error) {
            console.error(error);
            this.notification.add("Error al cerrar la sesión de conteo.", { type: "danger" });
        }
    }
}

CountInventoryApp.template = "digiflex_count_inventory.CountInventoryApp";
registry.category("actions").add("digiflex_count_inventory.app", CountInventoryApp);
