from odoo import tools, models, fields, api, _
from odoo.exceptions import ValidationError


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    device_id = fields.Char(string='Biometric Device ID')

class ZkMachine(models.Model):
    _name = 'zk.machine.attendance'
    _inherit = 'hr.attendance'

    device_id = fields.Char(string='Biometric Device ID')
    punch_type = fields.Selection([
        ('0', 'Check In'),
        ('1', 'Check Out'),
    ], string='Punching Type', required=True)
    attendance_type = fields.Selection([('1', 'Finger'),
                                        ('15', 'Face'),
                                        ('2','Type_2'),
                                        ('3','Password'),
                                        ('4','Card')], string='Category')
    punching_time = fields.Datetime(string='Punching Time', required=True)
    address_id = fields.Many2one('res.partner', string='Working Address')

    @api.constrains('employee_id', 'punch_type', 'punching_time')
    def _check_validity(self):
        for record in self:
            # Buscar el último registro del empleado
            last_attendance = self.search([
                ('employee_id', '=', record.employee_id.id),
                ('id', '!=', record.id)
            ], order='punching_time desc', limit=1)

            if last_attendance:
                # Validar que no se repitan dos registros consecutivos del mismo tipo
                if last_attendance.punch_type == record.punch_type:
                    raise ValidationError(_(
                        "No puedes registrar dos '%s' consecutivos para el empleado %s."
                    ) % (dict(record._fields['punch_type'].selection).get(record.punch_type),
                         record.employee_id.name))

                # Validar que Check Out no ocurra antes que el último Check In
                if record.punch_type == '1' and last_attendance.punch_type == '0' and \
                        record.punching_time <= last_attendance.punching_time:
                    raise ValidationError(_(
                        "La hora de Check Out debe ser después del último Check In para el empleado %s."
                    ) % record.employee_id.name)


class ReportZkDevice(models.Model):
    _name = 'zk.report.daily.attendance'
    _auto = False
    _order = 'punching_day desc'

    name = fields.Many2one('hr.employee', string='Employee')
    punching_day = fields.Date(string='Date')
    address_id = fields.Many2one('res.partner', string='Working Address')
    attendance_type = fields.Selection([('1', 'Finger'),
                                        ('15', 'Face'),
                                        ('2','Type_2'),
                                        ('3','Password'),
                                        ('4','Card')],
                                       string='Category')
    punch_type = fields.Selection([
        ('0', 'Check In'),
        ('1', 'Check Out'),
    ], string='Punching Type')
    punching_time = fields.Datetime(string='Punching Time')

    def init(self):
        tools.drop_view_if_exists(self._cr, 'zk_report_daily_attendance')
        query = """
            CREATE OR REPLACE VIEW zk_report_daily_attendance AS (
                SELECT
                    row_number() OVER () AS id,
                    z.employee_id AS name,
                    DATE_TRUNC('day', z.punching_time) AS punching_day,
                    z.address_id AS address_id,
                    z.attendance_type as attendance_type,
                    z.punch_type AS punch_type,
                    z.punching_time AS punching_time
                FROM zk_machine_attendance z
                WHERE z.punch_type IN ('0', '1')
                ORDER BY z.punching_time
            )
        """
        self._cr.execute(query)
