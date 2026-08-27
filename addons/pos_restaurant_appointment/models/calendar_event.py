# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models, fields


class CalendarEvent(models.Model):
    _inherit = "calendar.event"

    @api.model
    def _fields_for_restaurant_table(self):
        return [
            'id',
            'start',
            'duration',
            'stop',
            'name',
            'appointment_type_id',
            'appointment_resource_ids',
            'resource_total_capacity_reserved',
        ]


    @api.model
    def _send_table_notifications(self, events, command):
        # Build messages per bus channel in a single pass over events
        today = fields.Date.today()
        fields_to_read = self._fields_for_restaurant_table()
        messages_by_channel = {}

        for event in events:
            # Don't include the event if it's not for today
            if event.start.date() != today:
                continue

            event_dict = event.read(fields_to_read)[0]
            # tables that are booked for this event
            event_table_ids = event.booking_line_ids.appointment_resource_id.sudo().pos_table_ids
            for table in event_table_ids:
                for config in table.floor_id.pos_config_ids:
                    session = config.current_session_id
                    appt_type = event_dict.get('appointment_type_id')
                    if not session or not appt_type or appt_type[0] not in config.appointment_type_ids.ids:
                        continue

                    channel = session._get_bus_channel_name()
                    if channel not in messages_by_channel:
                        messages_by_channel[channel] = (
                            channel,
                            "TABLE_BOOKING",
                            {"command": command, "table_event_pairs": []},
                        )

                    messages_by_channel[channel][2]["table_event_pairs"].append([table.id, event_dict])

        messages = list(messages_by_channel.values())
        if len(messages) > 0:
            self.env['bus.bus']._sendmany(messages)

    @api.model_create_multi
    def create(self, vals_list):
        new_events = super().create(vals_list)
        self._send_table_notifications(new_events, "ADDED")
        return new_events

    def write(self, vals):
        self._send_table_notifications(self, "REMOVED")
        result = super().write(vals)
        self._send_table_notifications(self, "ADDED")
        return result

    def unlink(self):
        self._send_table_notifications(self, "REMOVED")
        return super().unlink()
