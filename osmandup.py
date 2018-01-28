#!/usr/bin/python

import sys
import os
import urllib2
import lxml.etree
import datetime
import re
import bisect
import time
import zipfile
import StringIO
import shutil

def print_usage(prog_name):
	sys.stdout.write('Usage: ' + prog_name + ' {--search regex, directory {--clean,--install regex,--list,--update}}\n')
	exit(-1)

def get_name(item_file):
	return item_file[item_file.find('>') + 1:-8]

def get_url(item_file):
	return 'https://download.osmand.net' + item_file[9:item_file.find('"',10)]

def get_item(line, offset):
	i = line.find('<td>', offset)
	if i == -1:
		return (None, offset)
	i += 4
	j = line.find('</td>', i)
	if j == -1:
		sys.stderr.write('\x1b[31m[!]\x1b[0m syntax error in list.php: corrupted item\n')
		return (None, offset)
	return (line[i:j], j + 5)

def get_line(data, offset):
	i = data.find('<tr>', offset)
	if i == -1:
		return (None, offset)
	i += 4
	j = data.find('</tr>', i)
	if j == -1:
		sys.stderr.write('\x1b[31m[!]\x1b[0m syntax error in list.php: corrupted line\n')
		return (None, offset)
	return (data[i:j], j + 5)

def get_netlist():
	result = []

	page_list = urllib2.urlopen('https://download.osmand.net/list.php').read()
	
	(line, line_offset) = get_line(page_list, 0)
	while line != None:
		(item_file, item_offset) = get_item(line, 0)
		(item_date, item_offset) = get_item(line, item_offset)
		(item_size, item_offset) = get_item(line, item_offset)
		(item_desc, item_offset) = get_item(line, item_offset)

		if item_file != None and item_date != None and item_size != None and item_desc != None:
			if item_desc != '' and not item_desc.startswith('Voice'):
				url = get_url(item_file)
				name = get_name(item_file)
				result.append([name, url, item_date, item_desc, int(float(item_size) * 1048576)])
		(line, line_offset) = get_line(page_list, line_offset)

	return sorted(result, key=lambda entry: entry[0])

def get_loclist(directory):
	result = []

	base_dir = os.path.join(directory, 'osmand')

	if not os.path.isdir(base_dir):
		sys.stderr.write('\x1b[31m[!]\x1b[0m unable to find map directory in ' + directory + '\n')
		exit(-1)

	files = []
	for (dir_path, dir_names, file_names) in os.walk(base_dir):
		files.extend(file_names)
		break

	files = [name for name in files if name.endswith('.obf')]

	for name in files:
		full_path = os.path.join(base_dir, name)
		modi_time = os.path.getmtime(full_path)
		file_size = os.path.getsize(full_path)

		result.append([name, full_path, modi_time, file_size])

	return sorted(result, key=lambda entry: entry[0])

def get_readable_size(size):
	if size > 1073741824:
		return str(size / 1073741824) + 'G'
	if size > 1048576:
		return str(size / 1048576) + 'M'
	elif size > 1024:
		return str(size / 1024) + 'K'
	return str(size)

def print_loclist(loclist):
	tot_size = 0
	for entry in loclist:
		date = datetime.datetime.fromtimestamp(entry[2]).strftime('%Y-%m-%d')
		sys.stdout.write(date + ' ' + entry[0][:-4].replace('_', ' ') + '\n')
		tot_size += entry[3]
	sys.stdout.write('Total size is \x1b[1m' + get_readable_size(tot_size) + '\x1b[0m\n')

def search_netlist(netlist, pattern):
	tot_size = 0
	for entry in netlist:
		m = re.search(pattern, entry[0], re.IGNORECASE)
		if m is not None:
			sys.stdout.write(entry[2] + ' ' + entry[0][:-4].replace('_', ' ').replace(m.group(0), '\x1b[31m' + m.group(0) + '\x1b[0m') + '\n')
			tot_size += entry[4]
	sys.stdout.write('Total size is \x1b[1m' + get_readable_size(tot_size) + '\x1b[0m\n')

def install_map(url, path):
	request = urllib2.urlopen(url)
	buf = StringIO.StringIO(request.read())
	zfile = zipfile.ZipFile(buf)
	for member in zfile.infolist():
		if path.endswith(member.filename):
			with open(path, 'wb') as outfile, zfile.open(member) as infile:
				shutil.copyfileobj(infile, outfile)

def update(loclist, netlist):
	dic = {net_entry[0] : i for i, net_entry in enumerate(netlist)}

	for loc_entry in loclist:
		if dic.has_key(loc_entry[0]):
			net_entry = netlist[dic[loc_entry[0]]]
			net_time = int(time.mktime(datetime.datetime.strptime(net_entry[2], "%d.%m.%Y").timetuple()))
			if loc_entry[2] < net_time:
				sys.stdout.write('\x1b[32m[+]\x1b[0m updating ' + loc_entry[0] + ' [' + net_entry[2] + ']\n')
				install_map(net_entry[1], loc_entry[1])
			else:
				sys.stdout.write('\x1b[36m[+]\x1b[0m ' + loc_entry[0] + 'is already up to date\n')
		else:
			sys.stdout.write('\x1b[31m[!]\x1b[0m ' + loc_entry[0] + ' is not distributed any more\n')

def clean(loclist, netlist, directory):
	for loc_entry in loclist:
		os.remove(loc_entry[1])
	for net_entry in netlist:
		if net_entry[0].find('World_base') != -1:
			sys.stdout.write('\x1b[32m[+]\x1b[0m installing ' + net_entry[0] + ' [' + net_entry[2] + ']\n')
			install_map(net_entry[1], os.path.join(directory, 'osmand', net_entry[0]))
			break

def install(loclist, netlist, directory, pattern):
	dic = {loc_entry[0] : i for i, loc_entry in enumerate(loclist)}

	for net_entry in netlist:
		m = re.search(pattern, net_entry[0], re.IGNORECASE)
		if m is not None:
			if dic.has_key(net_entry[0]):
				loc_entry = loclist[dic[net_entry[0]]]
				net_time = int(time.mktime(datetime.datetime.strptime(net_entry[2], "%d.%m.%Y").timetuple()))
				if loc_entry[2] < net_time:
					sys.stdout.write('\x1b[32m[+]\x1b[0m installing ' + net_entry[0] + ' [' + net_entry[2] + ']\n')
					install_map(net_entry[1], loc_entry[1])
				else:
					sys.stdout.write('\x1b[36m[+]\x1b[0m ' + net_entry[0] + 'is already installed and up to date\n')
			else:
				sys.stdout.write('\x1b[32m[+]\x1b[0m installing ' + net_entry[0] + ' [' + net_entry[2] + ']\n')
				install_map(net_entry[1], os.path.join(directory, 'osmand', net_entry[0]))

if __name__ == '__main__':
	if len(sys.argv) == 3 and sys.argv[1] == '--search':
		netlist = get_netlist()
		search_netlist(netlist, sys.argv[2])
		exit(0)

	if len(sys.argv) == 3 and sys.argv[2] == '--list':
		if not os.path.isdir(sys.argv[1]):
			sys.stderr.write('\x1b[31m[!]\x1b[0m ' + sys.argv[1] + ' is not a directory\n')
			exit(-1)
		loclist = get_loclist(sys.argv[1])
		print_loclist(loclist)
		exit(0)

	if len(sys.argv) == 3 and sys.argv[2] == '--update':
		if not os.path.isdir(sys.argv[1]):
			sys.stderr.write('\x1b[31m[!]\x1b[0m ' + sys.argv[1] + ' is not a directory\n')
			exit(-1)
		loclist = get_loclist(sys.argv[1])
		netlist = get_netlist()
		update(loclist, netlist)
		exit(0)

	if len(sys.argv) == 3 and sys.argv[2] == '--clean':
		if not os.path.isdir(sys.argv[1]):
			sys.stderr.write('\x1b[31m[!]\x1b[0m ' + sys.argv[1] + ' is not a directory\n')
			exit(-1)
		loclist = get_loclist(sys.argv[1])
		netlist = get_netlist()
		clean(loclist, netlist, sys.argv[1])
		exit(0)

	if len(sys.argv) == 4 and sys.argv[2] == '--install':
		if not os.path.isdir(sys.argv[1]):
			sys.stderr.write('\x1b[31m[!]\x1b[0m ' + sys.argv[1] + ' is not a directory\n')
			exit(-1)
		loclist = get_loclist(sys.argv[1])
		netlist = get_netlist()
		install(loclist, netlist, sys.argv[1], sys.argv[3])
		exit(0)

	print_usage(sys.argv[0])
