/** @odoo-module **/

import { patch } from '@web/core/utils/patch';

import { GridTimesheetTimerHeader } from '@timesheet_grid/components/grid_timesheet_timer_header/grid_timesheet_timer_header';

patch(GridTimesheetTimerHeader.prototype, {
    /**
     * @override
     */
    get fieldNames() {
        return [...super.fieldNames, 'helpdesk_ticket_id'];
    },

    /**
     * @override
     */
    getFieldInfo(fieldName) {
        const fieldInfo = super.getFieldInfo(fieldName);

        if (fieldName === "helpdesk_ticket_id") {
            fieldInfo.context = `{'default_project_id': project_id}`;
        }

        return fieldInfo;
    },
});
