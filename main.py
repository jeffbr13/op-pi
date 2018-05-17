#!/usr/bin/env python
import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from enum import Enum

from dot3k.menu import Menu, MenuOption
import dothat.backlight as backlight
import dothat.lcd as lcd
import dothat.touch as nav
import usb.core
import usb.util

from text import Text


VENDOR = 0x2367
PRODUCT = 0x0002
USBID_OP1 = "*Teenage_OP-1*"
MOUNT_DIR = "/media/op1"
HOME = "/home/pi"
BACKUPS_DIR = os.path.join(HOME, "backups")


# mounting
def mount_device(source, target):
    ensure_dir(target)
    subprocess.run(
        'mount {} {}'.format(source, target),
        shell=True, check=True
    )


def unmount_device(target):
    subprocess.run(
        'umount {}'.format(target),
        shell=True, check=True
    )


def get_device_path():
    o = subprocess.run(
        'readlink --canonicalize /dev/disk/by-id/' + USBID_OP1,
        shell=True, stdout=subprocess.PIPE
    ).stdout.decode()
    if USBID_OP1 in o:
        raise RuntimeError("Error getting OP-1 mount path: {}".format(o))
    else:
        return o.rstrip()


# copying
def ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)


def get_visible_folders(d):
    return list(filter(lambda x: os.path.isdir(os.path.join(d, x)), get_visible_children(d)))


def get_visible_children(d):
    return list(filter(lambda x: x[0] != '.', os.listdir(d)))


def copytree(src, dst, symlinks=False, ignore=None):
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, symlinks, ignore)
        else:
            shutil.copy2(s, d)


def backup_files(source, destination):
    dstroot = os.path.join(destination, datetime.now().isoformat())
    ensure_dir(dstroot)
    for node in get_visible_children(source):
        src = os.path.join(source, node)
        dst = os.path.join(dstroot, node)
        print(" . from: {} to {}".format(src, dst))
        ensure_dir(dst)
        copytree(src, dst)


class BackupState(Enum):
    WAITING_FOR_BLOCK_DEVICE = 0
    MOUNTING_BLOCK_DEVICE = 1
    COPYING_FILES = 2
    UNMOUNTING_BLOCK_DEVICE = 3
    COMPLETE = 4


class BackupMenuOption(MenuOption):
    def __init__(self):
        self.state = BackupState.WAITING_FOR_BLOCK_DEVICE
        super().__init__()

    def begin(self):
        backlight.rgb(237, 145, 33)  # Carrot-Orange

    def redraw(self, menu):
        backlight.set_graph(float(self.state.value) / float(BackupState.COMPLETE.value))

        if self.state == BackupState.WAITING_FOR_BLOCK_DEVICE:
            menu.write_row(0, 'Connect OP-1')
            menu.write_row(1, 'in Disk Mode:')
            menu.write_row(2, 'Shift+COM -> 3')
            if usb.core.find(idVendor=VENDOR, idProduct=PRODUCT):
                self.state = BackupState.MOUNTING_BLOCK_DEVICE

        elif self.state == BackupState.MOUNTING_BLOCK_DEVICE:
            menu.clear_row(0)
            menu.write_row(1, 'Mounting OP-1...')
            menu.clear_row(2)
            time.sleep(3)
            device_path = get_device_path()
            print(" > OP-1 device path: %s" % device_path)
            mount_device(device_path, MOUNT_DIR)
            print(" > Device mounted at %s" % MOUNT_DIR)
            self.state = BackupState.COPYING_FILES

        elif self.state == BackupState.COPYING_FILES:
            menu.clear_row(0)
            menu.write_row(1, 'Copying files...')
            menu.clear_row(2)
            backup_files(MOUNT_DIR, BACKUPS_DIR)
            self.state = BackupState.UNMOUNTING_BLOCK_DEVICE

        elif self.state == BackupState.UNMOUNTING_BLOCK_DEVICE:
            menu.clear_row(0)
            menu.write_row(1, 'Unmounting OP-1...')
            menu.clear_row(2)
            unmount_device(MOUNT_DIR)
            self.state = BackupState.COMPLETE

        elif self.state == BackupState.COMPLETE:
            menu.write_row(0, 'Back-up Done!')
            menu.clear_row(1)
            menu.write_row(2, '< Return')


class MIDIHostMenuOption(MenuOption):
    class State(Enum):
        UNCONNECTED = 0
        CONNECTED = 1

    @classmethod
    def build_aconnect_client_dict(cls, aconnect_output):
        client_strs = aconnect_output.strip().split('client ')[1:]
        ports = {}
        for client_str in client_strs:
            split = client_str.strip().split('\n')
            name, port_strs = split[0], split[1:]
            match = re.match(r"(?P<number>\d+): '(?P<name>[^']+)'", name)
            client_number = match.group('number')
            for port_str in port_strs:
                match = re.match(r"(?P<number>\d+) '(?P<name>[^']+)'", port_str.strip())
                port_number = match.group('number')
                port_name = match.group('name')
                ports['%s:%s' % (client_number, port_number)] = port_name.strip()
        return ports

    @classmethod
    def get_aconnect_inputs(cls):
        aconnect_output = subprocess.run(
            ['aconnect', '--input'],
            stdout=subprocess.PIPE,
        ).stdout.decode()
        return cls.build_aconnect_client_dict(
            aconnect_output
        )

    @classmethod
    def get_aconnect_outputs(cls):
        aconnect_output = subprocess.run(
            ['aconnect', '--output'],
            stdout=subprocess.PIPE,
        ).stdout.decode()
        return cls.build_aconnect_client_dict(
            aconnect_output
        )

    def __init__(self, in_port_name, in_port, out_port_name, out_port):
        self.state = self.State.UNCONNECTED
        self.in_port_name = in_port_name
        self.in_port = in_port
        self.out_port_name = out_port_name
        self.out_port = out_port
        super().__init__()

    def begin(self):
        backlight.rgb(180, 255, 120)    # green

    def redraw(self, menu):
        if self.state == self.State.UNCONNECTED:
            subprocess.run(
                ['aconnect', self.in_port, self.out_port],
                stdout=subprocess.PIPE
            )
            self.state = self.State.CONNECTED
        elif self.state == self.State.CONNECTED:
            menu.write_row(0, self.in_port_name)
            menu.write_row(1, 'connected to')
            menu.write_row(2, self.out_port_name)


class PowerOffMenuOption(MenuOption):
    def redraw(self, menu):
        menu.clear_row(0)
        menu.write_row(1, 'Powering off...')
        menu.clear_row(2)

        time.sleep(3)
        menu.write_row(0, 'Disconnect PWR')
        menu.write_row(1, 'once green LED')
        menu.write_row(2, 'stops flashing.')
        backlight.off()
        backlight.set_graph(0)
        subprocess.run('shutdown -h now', shell=True)


MIDI_INPUTS = MIDIHostMenuOption.get_aconnect_inputs()
MIDI_OUTPUTS = MIDIHostMenuOption.get_aconnect_outputs()

MENU = Menu(
    structure={
        'Backup All': BackupMenuOption(),
        # todo - per-tape backup/load?
        # 'Backup Tape': {
        #     'Tape 1': TapeBackupMenuOption(1),
        # }
        # todo - per-album-side backup/load?
        # 'Backup Album': {
        #     'Side A': ...,
        #     'Side B': ...,
        # },
        'MIDI Host': {
            in_name: {
                out_name: MIDIHostMenuOption(in_name, in_port, out_name, out_port)
                for out_port, out_name in MIDI_OUTPUTS.items()
            }
            for in_port, in_name in MIDI_INPUTS.items()
        },
        'Power Off': PowerOffMenuOption(),
    },
    lcd=lcd,
    input_handler=Text(),
)

if __name__ == '__main__':
    backlight.rgb(255, 255, 255)
    nav.bind_defaults(MENU)
    while True:
        MENU.redraw()
        time.sleep(0.05)
