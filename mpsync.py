import os
import sys
import time
import argparse
from io import StringIO
from mp.mpfshell import MpFileShell

def list_files_local(local_dir):
    local_files = []
    for root, _, files in os.walk(local_dir):
        for file in files:
            relative_path = os.path.relpath(os.path.join(root, file), local_dir)
            local_files.append(relative_path.replace(os.path.sep, '/'))
    return local_files

def capture_output(func, *args):
    old_stdout = sys.stdout
    sys.stdout = buffer = StringIO()
    try:
        func(*args)
    finally:
        sys.stdout = old_stdout
    return buffer.getvalue()

def get_file_stat_mp(mpfs, file_path):
    stat_command = f'import uos\nprint(uos.stat("{file_path}"))'
    stat_output = capture_output(mpfs.do_exec, stat_command)
    try:
        stat_values = eval(stat_output.strip().split('\n')[-1])
        return stat_values
    except (ValueError, IndexError):
        return None

def list_files_mp(mpfs, directory='', mp_folders=None):
    if mp_folders is None:
        mp_folders = set()
    mp_files = {}
    if directory:
        mpfs.do_cd(directory)
    mp_files_output = capture_output(mpfs.do_ls, '')
    lines = mp_files_output.splitlines()
    for line in lines[3:]:
        type = line[1:6]
        node = line[7:]
        if len(node) > 0:
            if type == '<dir>':
                folder = node
                if folder == '..':
                    continue
                sub_directory = f"{directory}/{folder}".replace('//', '/')
                mp_folders.add(sub_directory)
                sub_files, sub_folders = list_files_mp(mpfs, sub_directory, mp_folders)
                mp_files.update(sub_files)
                mp_folders.update(sub_folders)
            else:
                filename = node
                file_path = f"{directory}/{filename}".replace('//', '/')
                stat_values = get_file_stat_mp(mpfs, file_path)
                if stat_values:
                    mtime = stat_values[8]
                    mp_files[file_path] = mtime
    if directory:
        mpfs.do_cd('..')
    return mp_files, mp_folders


def split_path(path):
    parts = []
    while path:
        parts.insert(0, path)
        path, _ = os.path.split(path)
        if path == '' or path == '/':
            break
    return parts
    

def create_remote_folder(mpfs, folder_path, mp_folders):
    try:
        paths = split_path(folder_path)
        for path in paths:
            if path not in mp_folders:
                mpfs.do_md(path)
    except Exception as e:
        print(f"Could not create folder {folder_path}: {e}")

def upload_file(mpfs, local_path, mp_path, mp_folders):
    mp_dir = os.path.dirname(mp_path)
    if mp_dir and mp_dir not in mp_folders:
        create_remote_folder(mpfs, mp_dir, mp_folders)
        mp_folders.add(mp_dir)
    mpfs.do_put(f'{local_path} {mp_path}')

def sync_time(mpfs):
    print('Setting time...')
    n = time.gmtime(time.time())
    stat_command = 'import machine\n'
    stat_command += 'import utime\n'
    stat_command += 'rtc=machine.RTC()\n'
    stat_command += 'rtc.datetime(('
    stat_command += f'{n.tm_year}, {n.tm_mon}, {n.tm_mday}, {n.tm_wday}, {n.tm_hour}, {n.tm_min}, {n.tm_sec}'
    stat_command += ', 0))\n'
    stat_command += 'print(rtc.datetime())'
    mpfs.do_exec(stat_command)

def update_files(mp_port, local_dir, mp_dir):
    mpfs = MpFileShell()
    if mpfs.do_open(f'{mp_port}') == False:
        print(f'Unable to connect to MicroPython device at {mp_port}')
        return False
    
    sync_time(mpfs)
    
    print('Scanning files...')
    mp_files, mp_folders = list_files_mp(mpfs)
    local_files = list_files_local(local_dir)
    mp_folders.add('/')

    updated_files = 0
    for file in local_files:
        local_path = os.path.join(local_dir, file).replace('\\', '/')
        mp_path = f'{mp_dir}/{file}'.replace('//', '/')

        local_mtime = int(os.path.getmtime(local_path)) - 946684800
        mp_mtime = mp_files.get(mp_path)

        if mp_mtime is None:
            print(f'Uploading new file: {file}')
            upload_file(mpfs, local_path, mp_path, mp_folders)
            updated_files += 1
        elif local_mtime > mp_mtime:
            print(f'Updating file: {file}')
            upload_file(mpfs, local_path, mp_path, mp_folders)
            updated_files += 1

    mpfs.do_close('')
    if updated_files == 0:
        print('Files already up to date.')

def main():
    parser = argparse.ArgumentParser(description='Sync local files to a MicroPython device.')
    parser.add_argument('mp_port', help='MicroPython device port (e.g., COM10, /dev/ttyUSB0)')
    parser.add_argument('--local_dir', default=os.getcwd(), help='Local directory to sync (default: current directory)')
    parser.add_argument('--mp_dir', default='/', help='Directory on MicroPython device to sync to (default: /)')
    
    args = parser.parse_args()
    
    update_files(args.mp_port, args.local_dir, args.mp_dir)

if __name__ == '__main__':
    main()
