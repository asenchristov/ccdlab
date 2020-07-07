#!/usr/bin/env python3

import os
import sys

from daemon import SimpleFactory, SimpleProtocol, catch
from command import Command

from camlinlib import MonoChromator, GetPortAndPaths

# Camlin code with server daemon and outgoing connection to hardware


class DaemonProtocol(SimpleProtocol):
    _debug = False  # Display all traffic for debug purposes
    lampDict = {'Xe': 0, 'W': 1, 0: 'Xe', 1: 'W'}

    @catch
    def processMessage(self, string):
        # It will handle some generic messages and return pre-parsed Command object
        cmd = SimpleProtocol.processMessage(self, string)
        if cmd is None:
            return

        obj = self.object  # Object holding the state
        hw = obj['hw']  # HW factory
        if cmd.name == 'get_status':
            keys = ['hw_connected', 'lamp', 'wavelength', 'grating', 'grooves', 'blaze', 'filter', 'shutter', 'autofilter']

            self.message('status ' + ' '.join([_+'='+str(obj.get(_)) for _ in keys]))
        while obj['hw_connected']:
            # Accept commands only when HW is connected
            if string.startswith('set filter'):
                val = int(string.split('=')[1])
                if obj.get('filter') != val:
                    if hw.set_filterwheel_position(obj['hw_filterwheel'], filter) != 0:
                        self.factory.log(hw.GetErrorName(hw.result))
                break
            if string.startswith('set autofilter'):
                val = int(string.split('=')[1])
                obj['autofilter'] = val
                break

            if string.startswith('set shutter'):
                val = int(string.split('=')[1])
                self.factory.log('Setting shutter to %d' % shutter)
                if (val and hw.open_shutter(obj['hw_shutter']) != 0) or (not val and hw.close_shutter(obj['hw_shutter']) != 0):
                    self.factory.log(hw.GetErrorName(hw.result))
                break
            grval = obj['grating']
            wvlval = obj['wavelength']
            if string.startswith('set grating'):
                grval = int(string.split('=')[1])
            if string.startswith('set wavelength'):
                wvlval = float(string.split('=')[1])
            if grval != obj.get('grating') or wvlval != obj.get('wavelength'):
                self.factory.log("Moving grating %d to wavelength %g" % (grating, wavelength))
                if hw.move_to_wavelength(grating, wavelength) != 0:
                    self.factory.log(hw.GetErrorName(hw.result))
                if obj['autofilter']:
                    filters = [None, 395, 695, 1000, None, None]
                    filter = 1
                    for _, __ in enumerate(filters):
                        if __ and __ < wavelength:
                            filter = _ + 1
                break
            if string.startswith('set lamp'):
                lamp = string.split('=')[1]
                self.factory.log('Swithing to '+lamp+' lamp')
                if hw.set_mirror_position(1, self.lampDict[lamp]) != 0:
                    self.factory.log(hw.GetErrorName(hw.result))
                break
            if string.startswith('init '):
                tti = string.split()[1]
                num = -1
                if tti == 'turret':
                    num = 1
                elif tti == 'filter':
                    num = 3
                elif tti == 'mirror':
                    num = 4
                if num != -1:
                    hw.initialise_device(num=num)
                else:
                    self.factory.log('unknown device to init: '+tti, type='info')
                break
            break

    @catch
    def update(self):
        hw = obj['hw']
        # print "update"
        if not obj['hw_connected']:
            res = hw.connect()
            if res == 0 or res == -19:
                obj['hw_connected'] = 1

                # Print some info
                print ("DLL:", hw.get_dll_version())
                print ("SN:", hw.get_serial_number())
                print ("Firmware:", hw.get_firmware_version())
                print ("Model:", hw.get_model())

                # Perform an initialization
                hw.initialise_device(1)
                hw.get_current_grating()
                hw.move_to_wavelength(1, 600)
                hw.close_shutter(obj['hw_shutter'])
                hw.set_filterwheel_position(obj['hw_filterwheel'], 1)
                obj['autofilter'] = 0

        if obj['hw_connected']:
            if hw.get_model() is None:
                obj['hw_connected'] = 0
                hw.disconnect()
            else:
                obj['lamp'] = self.lampDict[hw.get_mirror_position(1)]
                obj['wavelength'] = hw.get_wavelength()
                obj['grating'] = hw.get_current_grating()
                obj['grooves'] = hw.get_grooves(obj['grating'])
                obj['blaze'] = hw.get_blaze(obj['grating'])
                obj['filter'] = hw.get_filterwheel_position(obj['hw_filterwheel'])
                obj['shutter'] = 1 if hw.is_shutter_open(obj['hw_shutter']) else 0


if __name__ == '__main__':
    from optparse import OptionParser

    parser = OptionParser(usage="usage: %prog [options] arg")
    parser.add_option('-d', '--device', help='Serial device to connect', action='store', dest='device', default='/dev/monochromator')
    parser.add_option('-p', '--port', help='Daemon port', action='store', dest='port', type='int', default=7025)
    parser.add_option('-n', '--name', help='Daemon name', action='store', dest='name', default='camlin')
    parser.add_option("-D", '--debug', help='Debug mode', action="store_true", dest="debug")
    (options, args) = parser.parse_args()

    # Object holding actual state and work logic.
    # May be anything that will be passed by reference - list, dict, object etc
    obj = {'hw_connected': 0, 'autofilter': 1}

    # Factory for daemon connections
    daemon = SimpleFactory(DaemonProtocol, obj)
    daemon.name = options.name

    # Hardware
    device, libpath, calibpath = GetPortAndPaths()
    if options.device:
        device = options.device

    hw = MonoChromator(device, libpath, calibpath)

    obj['hw_device'] = device
    obj['hw_libpath'] = libpath
    obj['hw_calibpath'] = calibpath
    obj['hw_filterwheel'] = 2
    obj['hw_shutter'] = 2

    obj['daemon'] = daemon
    obj['hw'] = hw

    if options.debug:
        daemon._protocol._debug = True

    # Incoming connections
    daemon.listen(options.port)

    daemon._reactor.run()
