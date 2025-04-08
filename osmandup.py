#!/usr/bin/env python3

import sys
import os
import urllib.request
import datetime
import re
import time
import zipfile
from io import BytesIO
import shutil

USE_COLOR: bool = True

def str_red(str_: str) -> str:
    if USE_COLOR:
        return '\x1b[31m' + str_ + '\x1b[0m'
    return str_

def str_green(str_: str) -> str:
    if USE_COLOR:
        return '\x1b[32m' + str_ + '\x1b[0m'
    return str_

def str_orange(str_: str) -> str:
    if USE_COLOR:
        return '\x1b[33m' + str_ + '\x1b[0m'
    return str_

def str_blue(str_: str) -> str:
    if USE_COLOR:
        return '\x1b[36m' + str_ + '\x1b[0m'
    return str_

def str_bold(str_: str) -> str:
    if USE_COLOR:
        return '\x1b[1m' + str_ + '\x1b[0m'
    return str_

def str_name(name: str) -> str:
    if name.endswith('.obf'):
        name = name[:-4]
    return name.replace('_', ' ')

def str_size(size: int) -> str:
    if size > 1073741824:
        return str(size // 1073741824) + ' GiB'
    if size > 1048576:
        return str(size // 1048576) + ' MiB'
    if size > 1024:
        return str(size // 1024) + ' KiB'
    return str(size) + ' B'

def str_timestamp(timestamp: int) -> str:
    return str(datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d'))

def print_error(msg: str) -> None:
    sys.stderr.write(str_red('[!]') + ' ' + msg + '\n')

def print_success(msg: str) -> None:
    sys.stdout.write(str_green('[+]') + ' ' + msg + '\n')

def print_warning(msg: str) -> None:
    sys.stdout.write(str_orange('[~]') + ' ' + msg + '\n')

def print_skip(msg: str) -> None:
    sys.stdout.write(str_blue('[.]') + ' ' + msg + '\n')

def print_usage(prog_name: str) -> None:
    print(f'Usage: {prog_name} {{--search regex, directory {{--clean,--install regex,--list,--update}}}}')
    sys.exit(-1)

def get_name(item_file: bytes) -> str:
    name = item_file[item_file.find(b'>') + 1:-8].decode('utf-8')
    if name.endswith('_2.obf'):
        name = name[:-6] + '.obf'
    return name

def get_url(item_file: bytes) -> str:
    path = item_file[9:item_file.find(b'"', 10)].decode('utf-8')
    path = path.replace('&amp;', '&')
    return 'https://download.osmand.net' + path

def get_size(item_size: bytes) -> int:
    return int(float(item_size) * 1048576)

def get_timestamp(item_date: bytes) -> int:
    date = item_date.decode('utf-8')
    return int(time.mktime(datetime.datetime.strptime(date, '%d.%m.%Y').timetuple()))

def get_item(line: bytes, offset: int) -> tuple:
    i = line.find(b'<td>', offset)
    if i == -1:
        return (None, offset)
    i += 4
    j = line.find(b'</td>', i)
    if j == -1:
        print_error('syntax error in list.php: corrupted item')
        return (None, offset)
    return (line[i:j].strip(), j + 5)

def get_lines(data: bytes):
    offset = 0
    while True:
        i = data.find(b'<tr>', offset)
        if i == -1:
            break
        i += 4
        j = data.find(b'</tr>', i)
        if j == -1:
            print_error('syntax error in list.php: corrupted line')
            break
        yield data[i:j]
        offset = j + 5

def get_netlist() -> list:
    result = []

    with urllib.request.urlopen('https://download.osmand.net/list.php') as request:
        for line in get_lines(request.read()):
            (item_file, item_offset) = get_item(line, 0)
            if item_file is None:
                continue
            (item_date, item_offset) = get_item(line, item_offset)
            if item_date is None:
                continue
            (item_size, item_offset) = get_item(line, item_offset)
            if item_size is None:
                continue
            (item_desc, item_offset) = get_item(line, item_offset)
            if item_desc is None:
                continue

            if item_desc and not item_desc.startswith(b'Voice'):
                name = get_name(item_file)
                url = get_url(item_file)
                size = get_size(item_size)
                timestamp = get_timestamp(item_date)
                result.append((name, url, timestamp, item_desc.decode('utf-8'), size))

    return sorted(result, key=lambda entry: entry[0])

def get_loclist(directory: str) -> list:
    result = []

    files = []
    for (_, _, file_names) in os.walk(directory):
        files.extend(file_names)
        break

    files = [name for name in files if name.endswith('.obf')]

    for name in files:
        full_path = os.path.join(directory, name)
        modi_time = os.path.getmtime(full_path)
        file_size = os.path.getsize(full_path)

        result.append([name, full_path, modi_time, file_size])

    return sorted(result, key=lambda entry: entry[0])

def print_loclist(loclist: list) -> None:
    tot_size: int = 0
    for entry in loclist:
        print(str_timestamp(entry[2]) + ' ' + str_name(entry[0]))
        tot_size += entry[3]
    print('Total installed size is ' + str_bold(str_size(tot_size)))

def search_netlist(netlist: list, pattern: str) -> None:
    tot_size: int = 0
    for entry in netlist:
        m = re.search(pattern, entry[0], re.IGNORECASE)
        if m is not None:
            print(str_timestamp(entry[2]) + ' ' + str_name(entry[0]).replace(m.group(0), str_red(m.group(0))))
            tot_size += entry[4]
    print('Total compressed size is ' + str_bold(str_size(tot_size)))

def install_map(url: str, path: str) -> None:
    with urllib.request.urlopen(url) as request:
        buf = BytesIO(request.read())
    with zipfile.ZipFile(buf) as zfile:
        for member in zfile.infolist():
            filename = member.filename
            if filename.endswith('_2.obf'):
                filename = filename[:-6] + '.obf'
            if path.endswith(filename):
                with open(path, 'wb') as outfile, zfile.open(member) as infile:
                    shutil.copyfileobj(infile, outfile)

def update(loclist: list, netlist: list) -> None:
    dic = {net_entry[0] : net_entry for net_entry in netlist}

    for loc_entry in loclist:
        if loc_entry[0] in dic:
            net_entry = dic[loc_entry[0]]
            if loc_entry[2] < net_entry[2]:
                print_success(f'updating {str_name(loc_entry[0])} [{str_timestamp(net_entry[2])}]')
                install_map(net_entry[1], loc_entry[1])
            else:
                print_skip(str_name(loc_entry[0]) + ' is already up to date')
        else:
            print_error(str_name(loc_entry[0]) + ' is not distributed any more')

def clean(loclist: list, netlist: list, directory: str) -> None:
    for loc_entry in loclist:
        os.remove(loc_entry[1])
    install([], netlist, directory, 'World_basemap')

def install(loclist: list, netlist: list, directory: str, pattern: str) -> None:
    dic = {loc_entry[0] : loc_entry for loc_entry in loclist}

    for net_entry in netlist:
        if re.search(pattern, net_entry[0], re.IGNORECASE) is None:
            continue
        if net_entry[0] in dic:
            loc_entry = dic[net_entry[0]]
            if loc_entry[2] < net_entry[2]:
                print_success(f'installing {str_name(net_entry[0])} [{str_timestamp(net_entry[2])}]')
                install_map(net_entry[1], loc_entry[1])
            else:
                print_skip(str_name(net_entry[0]) + ' is already installed and up to date')
        else:
            print_success(f'installing {str_name(net_entry[0])} [{str_timestamp(net_entry[2])}]')
            install_map(net_entry[1], os.path.join(directory, net_entry[0]))

def main() -> None:
    if len(sys.argv) < 3:
        print_usage(sys.argv[0])

    if sys.argv[1] == '--search':
        search_netlist(get_netlist(), sys.argv[2])
        sys.exit(0)

    directory = sys.argv[1]
    if not os.path.isdir(directory):
        print_error(f'{directory} is not a directory')
        sys.exit(-1)

    loclist = get_loclist(directory)

    if sys.argv[2] == '--list':
        print_loclist(loclist)
        sys.exit(0)

    if sys.argv[2] == '--update':
        update(loclist, get_netlist())
        sys.exit(0)

    if sys.argv[2] == '--clean':
        clean(loclist, get_netlist(), directory)
        sys.exit(0)

    if sys.argv[2] == '--install' and len(sys.argv) == 4:
        install(loclist, get_netlist(), directory, sys.argv[3])
        sys.exit(0)

    print_usage(sys.argv[0])

if __name__ == '__main__':
    if os.environ.get('NO_COLOR'):
        USE_COLOR = False
    main()
