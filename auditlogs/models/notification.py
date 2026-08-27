import os
import base64
import subprocess
from odoo import _, api, fields, models
from datetime import datetime, timedelta
from tempfile import NamedTemporaryFile, gettempdir

class AuditlogConfig(models.Model):
    _name = "auditlog.config"
    _description = "Auditlog Configuration"
    _rec_name = "model_id"
    
    model_id = fields.Many2one(
    "ir.model", 
    string="Model", 
    index=True, 
    ondelete="set null", 
    help="Select the model for which you want to receive the alert notifications via email."
    )
    notify_on_delete = fields.Boolean(
        "Notify on Delete", 
        help="Enable this option to receive an alert when a record is deleted."
    )
    notify_on_update = fields.Boolean(
        "Notify on Update", 
        help="Enable this option to receive an alert when a record is updated."
    )
    alert_threshold = fields.Integer(
        "Alert Threshold", 
        default=50, 
        help="Set the threshold value at which an alert will be triggered."
    )
    alert_timeframe = fields.Integer(
        "Alert Timeframe (hours)", 
        default=12, 
        help="Set the time window (in hours) within which the alert should be triggered."
    )


class AuditlogNotification(models.Model):
    _inherit = "auditlog.log"

    def _check_alerts(self, config, current_time):
        """
        Check if the number of deletions exceeds the threshold within the alert time frame.
        If exceeded, send an alert email.
        """
        start_time = current_time - timedelta(hours=config.alert_timeframe)
        
        deletion_count = self.search_count([('create_date', '>=', start_time),
                                            ('model_id', '=', config.model_id.id)])
        
        if deletion_count > config.alert_threshold:
            self._send_alert(config, deletion_count)
            return True 
        return False  

    def _send_alert(self, config, deletion_count):
        greeting = _("Hello, {}.").format(self.env.user.name)

        company_name = self.env.user.company_id.name
        company_email = self.env.user.company_id.email

        header = """
            <table style="width: 100%; background-color: #f4f4f4;">
                <tr>
                    <td style="text-align: center; padding: 20px; font-size: 24px; font-weight: bold;">
                        <span style="color: ##FF0000;">{}</span>
                    </td>
                </tr>
            </table>
            """.format(_('Alert'))

        message = f"""
        <p>{greeting}</p>
        <p>{_('This is a notification regarding the recent deletion of logs in your system.')}</p>
        <p>{_('We have detected a high number of deletions in the last %d hours: High deletions occurred.') % (config.alert_timeframe)}</p>
        <p>{_('For your reference, the details of the deleted logs are included in the attached PDF document in next Mail.')}</p>
        <p>{_('Please review the attached PDF for the full list of deleted logs and additional details.')}</p>
        <p>{_('The PDF includes log names, resource IDs, and the users who performed the deletions.')}</p>
        <p>{_('Kindly refer to the document for more in-depth information about the deletions in your system.')}</p>
        """

        signature = """
            <br/>
            <p>{}</p>
            <p><strong>{}</strong></p>
            <p>{}</p>
            <p>{}</p>
            <p>{}</p>
        """.format(_('Best regards,'), self.env.user.name, company_name,  _('Contact us:'), company_email,)

        full_body_html = header + message + signature

        mail_values = {
            'subject': _("Alert- High Deletion of Logs"),
            'body_html': full_body_html,
            'email_to': self.env.user.email,
        }

        mail = self.env['mail.mail'].create(mail_values)
        mail.send()

    def unlink(self):
        deletion_records = self.read(['name', 'model_name', 'res_id', 'user_id'])
        if not deletion_records:
            return super(AuditlogNotification, self).unlink()

        deletion_sent = False
        current_time = datetime.now()

        for record in self:
            config = self.env["auditlog.config"].search([("model_id", "=", record.model_id.id)], limit=1)
            
            if config and config.notify_on_delete and not deletion_sent:
                self._check_alerts(config, current_time)
                deletion_sent = True

        deletion_info = []
        for record in deletion_records:
            deletion_info.append({
                'name': record['name'],
                'model_name': record['model_name'],
                'res_id': record['res_id'],
                'user': self.env['res.users'].browse(record['user_id'][0]).name if record['user_id'] else _('Unknown'),
            })

        html_content = """
        <html>
            <body>
                <h1>{}</h1>
                <table border="1">
                    <thead>
                        <tr>
                            <th>{}</th>
                            <th>{}</th>
                            <th>{}</th>
                            <th>{}</th>
                        </tr>
                    </thead>
                    <tbody>
        """.format(_('Deleted Logs Report'), _('Log Name'), _('Model'), _('Resource ID'), _('Deleted by'))

        for info in deletion_info:
            html_content += f"""
            <tr>
                <td>{info['name']}</td>
                <td>{info['model_name']}</td>
                <td>{info['res_id']}</td>
                <td>{info['user']}</td>
            </tr>
            """

        html_content += """
                    </tbody>
                </table>
            </body>
        </html>
        """

        with NamedTemporaryFile(delete=False, mode='w', encoding='utf-8', suffix='.html') as tmp_html_file:
            tmp_html_file.write(html_content)
            tmp_html_file_path = tmp_html_file.name

        pdf_dir = gettempdir() 
        if not os.path.exists(pdf_dir):
            os.makedirs(pdf_dir)

        pdf_file_path = os.path.join(pdf_dir, 'deleted_logs_report.pdf')

        try:
            subprocess.run(['wkhtmltopdf', tmp_html_file_path, pdf_file_path])

            with open(pdf_file_path, 'rb') as file:
                pdf_data = file.read()

            attachment = {
                'name': _('deleted_logs.pdf'),
                'datas': base64.b64encode(pdf_data),
                'type': 'binary',
                'mimetype': 'application/pdf',
            }

            name = _("Hello, {}.").format(self.env.user.name)
            body_part1 = _("Please find the attached PDF for the deleted logs.")
            body_part2 = "<br>"
            company_name = self.env.user.company_id.name
            signature = """
                <p>{}</p>
                <p><strong>{}</strong></p>
                <p>{}</p>
            """.format(_('Best regards,'), self.env.user.name, company_name)

            full_body_html = f"""
            <html>
                <body>
                    <p>{name}</p>
                    <p>{body_part1}</p>
                    <p>{body_part2}</p>
                    <p>{signature}</p>
                </body>
            </html>
            """
            
            mail_values = {
                'subject': _("Notification- Logs Deleted"),
                'body_html': full_body_html,
                'email_to': self.env.user.email,
                'attachment_ids': [(0, 0, attachment)],
            }
            mail = self.env['mail.mail'].create(mail_values)
            mail.send()

        except Exception as e:
            _logger = self.env['ir.logging'].sudo()
            _logger.create({
                'name': 'Auditlog Notification Error',
                'type': 'error',
                'message': str(e),
                'level': 'ERROR',
            })

        return super(AuditlogNotification, self).unlink()
