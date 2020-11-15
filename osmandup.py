#!/usr/bin/python3

import sys
import os
import urllib.request
import datetime
import re
import time
import zipfile
from io import BytesIO
import shutil

USE_COLOR = True

def str_red(str_):
	if USE_COLOR:
		return '\x1b[31m' + str_ + '\x1b[0m'
	return str_

def str_green(str_):
	if USE_COLOR:
		return '\x1b[32m' + str_ + '\x1b[0m'
	return str_

def str_orange(str_):
	if USE_COLOR:
		return '\x1b[33m' + str_ + '\x1b[0m'
	return str_

def str_blue(str_):
	if USE_COLOR:
		return '\x1b[36m' + str_ + '\x1b[0m'
	return str_

def str_bold(str_):
	if USE_COLOR:
		return '\x1b[1m' + str_ + '\x1b[0m'
	return str_

def print_error(msg):
	sys.stderr.write(str_red('[!]') + ' ' + msg + '\n')

def print_success(msg):
	sys.stdout.write(str_green('[+]') + ' ' + msg + '\n')

def print_warning(msg):
	sys.stdout.write(str_orange('[~]') + ' ' + msg + '\n')

def print_skip(msg):
	sys.stdout.write(str_blue('[.]') + ' ' + msg + '\n')

def print_usage(prog_name):
	print('Usage: ' + prog_name + ' {--search regex, directory {--clean,--install regex,--list,--update}}')
	exit(-1)

def get_name(item_file):
	return item_file[item_file.find(b'>') + 1:-8].decode('utf-8')

def get_url(item_file):
	path = item_file[9:item_file.find(b'"', 10)].decode('utf-8')
	path = path.replace('&amp;', '&')
	return 'https://download.osmand.net' + path

def get_size(item_size):
	return int(float(item_size) * 1048576)

def get_item(line, offset):
	i = line.find(b'<td>', offset)
	if i == -1:
		return (None, offset)
	i += 4
	j = line.find(b'</td>', i)
	if j == -1:
		print_error('syntax error in list.php: corrupted item')
		return (None, offset)
	return (line[i:j].strip(), j + 5)

def get_lines(data):
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

def get_netlist():
	result = []

	page_list = urllib.request.urlopen('https://download.osmand.net/list.php').read()

	for line in get_lines(page_list):
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
			url = get_url(item_file)
			name = get_name(item_file)
			size = get_size(item_size)
			result.append([name, url, item_date.decode('utf-8'), item_desc.decode('utf-8'), size])

	return sorted(result, key=lambda entry: entry[0])

def get_loclist(directory):
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

def get_readable_size(size):
	if size > 1073741824:
		return str(size // 1073741824) + ' GB'
	if size > 1048576:
		return str(size // 1048576) + ' MB'
	if size > 1024:
		return str(size // 1024) + ' KB'
	return str(size)

def print_loclist(loclist):
	tot_size = 0
	for entry in loclist:
		date = datetime.datetime.fromtimestamp(entry[2]).strftime('%Y-%m-%d')
		print(date + ' ' + entry[0][:-4].replace('_', ' '))
		tot_size += entry[3]
	print('Total installed size is ' + str_bold(get_readable_size(tot_size)))

def search_netlist(netlist, pattern):
	tot_size = 0
	for entry in netlist:
		m = re.search(pattern, entry[0], re.IGNORECASE)
		if m is not None:
			print(entry[2] + ' ' + entry[0][:-4].replace('_', ' ').replace(m.group(0), str_red(m.group(0))))
			tot_size += entry[4]
	print('Total compressed size is ' + str_bold(get_readable_size(tot_size)))

def install_map(url, path):
	request = urllib.request.urlopen(url)
	buf = BytesIO(request.read())
	zfile = zipfile.ZipFile(buf)
	for member in zfile.infolist():
		if path.endswith(member.filename):
			with open(path, 'wb') as outfile, zfile.open(member) as infile:
				shutil.copyfileobj(infile, outfile)

def update(loclist, netlist):
	dic = {net_entry[0] : i for i, net_entry in enumerate(netlist)}

	for loc_entry in loclist:
		if loc_entry[0] in dic:
			net_entry = netlist[dic[loc_entry[0]]]
			net_time = int(time.mktime(datetime.datetime.strptime(net_entry[2], '%d.%m.%Y').timetuple()))
			if loc_entry[2] < net_time:
				print_success('updating ' + loc_entry[0] + ' [' + net_entry[2] + ']')
				install_map(net_entry[1], loc_entry[1])
			else:
				print_skip(loc_entry[0] + ' is already up to date')
		else:
			print_error('is not distributed any more')

def clean(loclist, netlist, directory):
	for loc_entry in loclist:
		os.remove(loc_entry[1])
	for net_entry in netlist:
		if net_entry[0].find('World_base') != -1:
			print_success('installing ' + net_entry[0] + ' [' + net_entry[2] + ']')
			install_map(net_entry[1], os.path.join(directory, net_entry[0]))
			return

def install(loclist, netlist, directory, pattern):
	dic = {loc_entry[0] : i for i, loc_entry in enumerate(loclist)}

	for net_entry in netlist:
		m = re.search(pattern, net_entry[0], re.IGNORECASE)
		if m is not None:
			if net_entry[0] in dic:
				loc_entry = loclist[dic[net_entry[0]]]
				net_time = int(time.mktime(datetime.datetime.strptime(net_entry[2], '%d.%m.%Y').timetuple()))
				if loc_entry[2] < net_time:
					print_success('installing ' + net_entry[0] + ' [' + net_entry[2] + ']')
					install_map(net_entry[1], loc_entry[1])
				else:
					print_skip(net_entry[0] + 'is already installed and up to date')
			else:
				print_success('installing ' + net_entry[0] + ' [' + net_entry[2] + ']')
				install_map(net_entry[1], os.path.join(directory, net_entry[0]))

if __name__ == '__main__':
	if os.environ.get('NO_COLOR'):
		USE_COLOR = False

	if len(sys.argv) < 3:
		print_usage(sys.argv[0])

	if sys.argv[1] == '--search':
		search_netlist(get_netlist(), sys.argv[2])
		exit(0)

	directory = sys.argv[1]
	if not os.path.isdir(directory):
		print_error(directory + ' is not a directory')
		exit(-1)

	while True:
		if os.path.isdir(os.path.join(directory, 'osmand')):
			directory = os.path.join(directory, 'osmand')
		else:
			break

	if os.path.basename(directory) != 'osmand':
		print_warning(directory + ' does not seem to be an osmand directory')

	loclist = get_loclist(directory)

	if sys.argv[2] == '--list':
		print_loclist(loclist)
		exit(0)

	if sys.argv[2] == '--update':
		update(loclist, get_netlist())
		exit(0)

	if sys.argv[2] == '--clean':
		clean(loclist, get_netlist(), directory)
		exit(0)

	if sys.argv[2] == '--install' and len(sys.argv) == 4:
		install(loclist, get_netlist(), directory, sys.argv[3])
		exit(0)

	print_usage(sys.argv[0])
