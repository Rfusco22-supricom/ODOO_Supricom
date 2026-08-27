# Part of Odoo. See LICENSE file for full copyright and licensing details.
from pytz import timezone, UTC
from collections import defaultdict

from odoo import models, fields, api
from odoo.addons.resource.models.utils import string_to_datetime, timezone_datetime, Intervals
from odoo.osv import expression
from odoo.tools import float_is_zero
from dateutil.relativedelta import relativedelta

class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    color = fields.Integer("Color", compute='_compute_color')
    overtime_progress = fields.Float(compute="_compute_overtime_progress")

    def _compute_overtime_progress(self):
        for attendance in self:
            if not float_is_zero(attendance.worked_hours, precision_digits=2):
                attendance.overtime_progress = 100 - ((attendance.overtime_hours / attendance.worked_hours) * 100)
            else:
                attendance.overtime_progress = 100

    @api.model
    def gantt_progress_bar(self, fields, res_ids, date_start_str, date_stop_str):
        if not self.user_has_groups("base.group_user"):
            return {field: {} for field in fields}

        start_utc, stop_utc = string_to_datetime(date_start_str), string_to_datetime(date_stop_str)

        progress_bars = {field: self._gantt_progress_bar(field, res_ids[field], start_utc, stop_utc) for field in fields}
        return progress_bars

    def _gantt_progress_bar(self, field, res_ids, start, stop):
        if field == 'employee_id':
            return self._gantt_progress_bar_employee_ids(res_ids, start, stop)
        raise NotImplementedError

    def _get_gantt_progress_bar_domain(self, res_ids, start, stop):
        domain = [
            ('employee_id', 'in', res_ids),
            ('check_in', '>=', start),
            ('check_out', '<=', stop)
        ]
        return domain

    def _gantt_progress_bar_employee_ids(self, res_ids, start, stop):
        """
        Resulting display is worked hours / expected worked hours
        """
        values = {}
        worked_hours_group = self._read_group(
            self._get_gantt_progress_bar_domain(res_ids, start, stop),
            groupby=['employee_id'],
            aggregates=['worked_hours:sum']
        )
        employee_data = {emp.id: worked_hours for emp, worked_hours in worked_hours_group}
        employees = self.env['hr.employee'].browse(res_ids)
        for employee in employees:
            # Retrieve expected attendance for that employee
            values[employee.id] = {
                'value': employee_data.get(employee.id, 0),
                'max_value': self.env['resource.calendar']._get_attendance_intervals_days_data(employee._get_expected_attendances(start, stop))['hours'],
            }

        return values

    @api.model
    def get_gantt_data(self, domain, groupby, read_specification, limit=None, offset=0):
        """
        We override get_gantt_data to allow the display of open-ended records,
        We also want to add in the gantt rows, the active emloyees that have a check in in the previous 7 days
        """
        user_domain = self.env.context.get('user_domain')
        start_date = self.env.context.get('gantt_start_date')

        open_ended_gantt_data = super().get_gantt_data(domain, groupby, read_specification, limit=limit, offset=offset)

        if start_date and groupby and groupby[0] == 'employee_id':
            active_employees_domain = expression.AND([
                user_domain,
                [
                    '&',
                    ('check_out', '<', start_date),
                    ('check_in', '>', fields.Datetime.from_string(start_date) - relativedelta(days=7)),
                    ('employee_id', 'not in', [group['employee_id'][0] for group in open_ended_gantt_data['groups']])
                ]])
            previously_active_employees = super().get_gantt_data(active_employees_domain, groupby, read_specification, limit=None, offset=0)
            for group in previously_active_employees['groups']:
                del group['__record_ids']  # Records are not needed here
                open_ended_gantt_data['groups'].append(group)
                open_ended_gantt_data['length'] += 1

        return open_ended_gantt_data

    @api.model
    def gantt_unavailability(self, str_start_date, str_end_date, scale, group_bys=None, rows=None):
        def tag_employee_rows(rows):
            """
                Add `employee_id` key in rows and subsrows recursively if necessary
                :return: a set of ids with all concerned employees (subrows included)
            """
            employee_ids = set()
            for row in rows:
                group_bys = row.get('groupedBy')
                res_id = row.get('resId')
                if not group_bys:
                    continue
                # if employee_id is the first grouping attribute, we mark the row
                if group_bys[0] == 'employee_id' and res_id:
                    employee_id = res_id
                    employee_ids.add(employee_id)
                    row['employee_id'] = employee_id
                # else we recursively traverse the rows where employee_id appears in the group_by
                elif 'employee_id' in group_bys:
                    employee_ids.update(tag_employee_rows(row.get('rows')))
            return employee_ids

        def inject_unvailabilty(row):
            new_row = row.copy()
            employee_id = new_row.get('employee_id')
            if not employee_id:
                return new_row

            for sub_row in new_row.get('rows', []):
                sub_row['employee_id'] = employee_id
            new_row['rows'] = [inject_unvailabilty(inner_row) for inner_row in new_row.get('rows', [])]

            # When an employee doesn't have any calendar,
            # he is considered unavailable for the entire interval
            if employee_id not in unavailable_intervals_by_employees:
                new_row['unavailabilities'] = [{
                    'start': start_datetime.astimezone(UTC),
                    'stop': end_datetime.astimezone(UTC),
                }]
                return new_row

            # When an employee doesn't have a calendar for a part of the entire interval,
            # he will be unavailable for this part
            if employee_id in periods_without_calendar_by_employee:
                unavailable_intervals_by_employees[employee_id] |= periods_without_calendar_by_employee[employee_id]
            new_row['unavailabilities'] = [{
                'start': interval[0].astimezone(UTC),
                'stop': interval[1].astimezone(UTC),
            } for interval in unavailable_intervals_by_employees[employee_id]]
            return new_row

        start_datetime = fields.Datetime.from_string(str_start_date)
        end_datetime = fields.Datetime.from_string(str_end_date)
        employees_by_calendar = defaultdict(lambda: self.env['hr.employee'])
        rows_employees = self.env['hr.employee'].browse(list(tag_employee_rows(rows)))

        # Retrieve for each employee, their period linked to their calendars
        calendar_periods_by_employee = rows_employees._get_calendar_periods(
            timezone_datetime(start_datetime),
            timezone_datetime(end_datetime),
        )

        full_interval_UTC = Intervals([(
            start_datetime.astimezone(UTC),
            end_datetime.astimezone(UTC),
            self.env['resource.calendar'],
        )])

        # calculate the intervals not covered by employee-specific calendars.
        # store these uncovered intervals for each employee.
        # store by calendar, employees involved with them
        periods_without_calendar_by_employee = defaultdict(list)
        for employee, calendar_periods in calendar_periods_by_employee.items():
            employee_interval_UTC = Intervals([])
            for (start, stop, calendar) in calendar_periods:
                calendar_periods_interval_UTC = Intervals([(
                    start.astimezone(UTC),
                    stop.astimezone(UTC),
                    self.env['resource.calendar'],
                )])
                employee_interval_UTC |= calendar_periods_interval_UTC
                employees_by_calendar[calendar] |= employee
            interval_without_calendar = full_interval_UTC - employee_interval_UTC
            if interval_without_calendar:
                periods_without_calendar_by_employee[employee.id] = interval_without_calendar

        # retrieve, for each calendar, unavailability periods for employees linked to this calendar
        unavailable_intervals_by_calendar = {}
        for calendar, employees in employees_by_calendar.items():
            calendar_work_intervals = calendar._work_intervals_batch(
                timezone_datetime(start_datetime),
                timezone_datetime(end_datetime),
                resources=employees.resource_id,
                tz=timezone(calendar.tz)
            )
            full_interval = Intervals([(
                start_datetime.astimezone(timezone(calendar.tz)),
                end_datetime.astimezone(timezone(calendar.tz)),
                calendar
            )])
            unavailable_intervals_by_calendar[calendar] = {
                employee.id: full_interval - calendar_work_intervals[employee.resource_id.id]
                for employee in employees}

        # calculate employee's unavailability periods based on his calendar's periods
        # (e.g. calendar A on monday and tuesday and calendar b for the rest of the week)
        unavailable_intervals_by_employees = {}
        for employee, calendar_periods in calendar_periods_by_employee.items():
            employee_unavailable_full_interval = Intervals([])
            for (start, stop, calendar) in calendar_periods:
                interval = Intervals([(start, stop, self.env['resource.calendar'])])
                calendar_unavailable_interval_list = unavailable_intervals_by_calendar[calendar][employee.id]
                employee_unavailable_full_interval |= interval & calendar_unavailable_interval_list
            unavailable_intervals_by_employees[employee.id] = employee_unavailable_full_interval

        return [inject_unvailabilty(row) for row in rows]
