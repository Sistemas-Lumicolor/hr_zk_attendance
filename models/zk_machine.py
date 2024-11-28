# -*- coding: utf-8 -*-
###################################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#    Copyright (C) 2022-TODAY Cybrosys Technologies(<http://www.cybrosys.com>).
#    Author: cybrosys(<https://www.cybrosys.com>)
#
#    This program is free software: you can modify
#    it under the terms of the GNU Affero General Public License (AGPL) as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###################################################################################
import pytz
import datetime
import logging

from zk import ZK
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)
try:
    from zk import ZK, const
except ImportError:
    _logger.error("Please Install pyzk library.")

_logger = logging.getLogger(__name__)


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    device_id = fields.Char(string='Biometric Device ID')


class ZkMachine(models.Model):
    _name = 'zk.machine'
    
    name = fields.Char(string='Machine IP', required=True)
    port_no = fields.Integer(string='Port No', required=True)
    address_id = fields.Many2one('res.partner', string='Working Address')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.user.company_id.id)

    @api.model
    def clear_attendance(self):
        # Lógica para limpiar datos
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    @api.model
    def download_attendance(self):
        # Lógica para descargar datos
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
    
    def device_connect(self, zk):
        try:
            conn = zk.connect()
            return conn
        except Exception as e:
            _logger.error(f"Connection Error: {e}")
            return False

    @api.model
    def cron_download(self):
        machines = self.env['zk.machine'].search([])
        for machine in machines:
            machine.download_attendance()

    def download_attendance(self):
        _logger.info("++++++++++++Cron Executed++++++++++++++++++++++")
        zk_attendance = self.env['zk.machine.attendance']
        att_obj = self.env['hr.attendance']
        for info in self:
            machine_ip = info.name
            zk_port = info.port_no
            timeout = 15
            try:
                zk = ZK(machine_ip, port=zk_port, timeout=timeout, password=0, force_udp=False, ommit_ping=False)
            except NameError:
                raise UserError(_("Pyzk module not Found. Please install it with 'pip3 install pyzk'."))
            
            conn = self.device_connect(zk)
            if conn:
                try:
                    user = conn.get_users()
                except Exception as e:
                    user = False
                    _logger.error(f"Error getting users: {e}")
                
                try:
                    attendance = conn.get_attendance()
                except Exception as e:
                    attendance = False
                    _logger.error(f"Error getting attendance: {e}")
                
                if attendance:
                    for each in attendance:
                        atten_time = each.timestamp
                        atten_time = datetime.datetime.strptime(
                            atten_time.strftime('%Y-%m-%d %H:%M:%S'), '%Y-%m-%d %H:%M:%S')
                        local_tz = pytz.timezone(self.env.user.partner_id.tz or 'GMT')
                        local_dt = local_tz.localize(atten_time, is_dst=None)
                        utc_dt = local_dt.astimezone(pytz.utc)
                        atten_time = utc_dt.strftime("%Y-%m-%d %H:%M:%S")
                        
                        if user:
                            for uid in user:
                                if uid.user_id == each.user_id:
                                    get_user_id = self.env['hr.employee'].search(
                                        [('device_id', '=', each.user_id)])
                                    if get_user_id:
                                        duplicate_atten_ids = zk_attendance.search(
                                            [('device_id', '=', each.user_id), ('punching_time', '=', atten_time)])
                                        if duplicate_atten_ids:
                                            continue
                                        else:
                                            # Forzar el tipo de asistencia
                                            punch_type = each.punch
                                            if punch_type not in [0, 1]:
                                                punch_type = 0 if each.punch % 2 == 0 else 1

                                            zk_attendance.create({'employee_id': get_user_id.id,
                                                                  'device_id': each.user_id,
                                                                  'attendance_type': str(each.status),
                                                                  'punch_type': str(punch_type),
                                                                  'punching_time': atten_time,
                                                                  'address_id': info.address_id.id})

                                            att_var = att_obj.search([('employee_id', '=', get_user_id.id),
                                                                      ('check_out', '=', False)])
                                            if punch_type == 0:  # Check-in
                                                if not att_var:
                                                    att_obj.create({'employee_id': get_user_id.id,
                                                                    'check_in': atten_time})
                                            if punch_type == 1:  # Check-out
                                                if len(att_var) == 1:
                                                    att_var.write({'check_out': atten_time})
                                                else:
                                                    att_var1 = att_obj.search([('employee_id', '=', get_user_id.id)])
                                                    if att_var1:
                                                        att_var1[-1].write({'check_out': atten_time})

                                    else:
                                        employee = self.env['hr.employee'].create(
                                            {'device_id': each.user_id, 'name': uid.name})
                                        zk_attendance.create({'employee_id': employee.id,
                                                              'device_id': each.user_id,
                                                              'attendance_type': str(each.status),
                                                              'punch_type': str(punch_type),
                                                              'punching_time': atten_time,
                                                              'address_id': info.address_id.id})
                                        att_obj.create({'employee_id': employee.id,
                                                        'check_in': atten_time})
                                else:
                                    pass
                    conn.disconnect()
                    return True
                else:
                    raise UserError(_('Unable to get the attendance log, please try again later.'))
            else:
                raise UserError(_('Unable to connect, please check the parameters and network connections.'))