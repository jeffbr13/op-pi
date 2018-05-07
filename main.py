#!/usr/bin/env python
import os
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
        # 'Host MIDI': HostMidiMenuOption(),
        'Power Off': PowerOffMenuOption(),
    },
    lcd=lcd,
    input_handler=Text(),
)

if __name__ == '__main__':
    backlight.rgb(255, 255, 255)
    nav.bind_defaults(MENU)
    while 1:
        MENU.redraw()
        time.sleep(0.05)
