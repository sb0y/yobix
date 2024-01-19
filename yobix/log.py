import logging
import sys

def init_log(args):
	# Set level
	level_map = {"info": logging.INFO, "debug": logging.DEBUG, "error": logging.ERROR, "warning": logging.WARNING}
	if args.verbose:
		level = logging.INFO
	elif args.very_verbose:
		level = logging.DEBUG
	else:
		level = level_map[args.log_level]

	logging.basicConfig()
	logger = logging.getLogger()
	logger.setLevel(level)
	# remove all console handlers
	for handler in logger.handlers:
		if type(handler) is logging.StreamHandler:
			logger.removeHandler(handler)

	# create file handler which logs messages
	if (args.log != "console"):
		file_h = logging.FileHandler(args.log)
	# create console handler with a higher log level
	console_h = logging.StreamHandler(sys.stdout)

	# create formatter and add it to the handlers
	try:
		import colorlog
	except ImportError:
		formatter = logging.Formatter(
			'%(asctime)s [%(levelname)s][%(name)s:%(lineno)d][pid:%(process)d] %(message)s')
		console_formatter = logging.Formatter(
			'[%(levelname)s] [pid:%(process)d] %(message)s')
	else:
		if level == logging.DEBUG:
			console_format_str = (
				'[%(log_color)s%(levelname).1s%(reset)s] '
				'[%(cyan)s%(name)s:%(lineno)d%(reset)s] '
				'%(message_log_color)s%(message)s'
			)
			file_format_str = (
				'%(asctime)s '
				'[%(log_color)s%(levelname)s%(reset)s] '
				'[%(cyan)s%(name)s:%(lineno)d%(reset)s] '
				'%(message_log_color)s%(message)s'
			)
		else: 
			console_format_str = (
				'[%(log_color)s%(levelname).1s%(reset)s] '
				'[%(cyan)s%(name)s:%(lineno)d%(reset)s] '
				'%(message_log_color)s%(message)s'
			)
			file_format_str = (
				'%(asctime)s '
				'[%(log_color)s%(levelname)s%(reset)s] '
				'[%(cyan)s%(name)s:%(lineno)d%(reset)s] '
				'%(message_log_color)s%(message)s'
			)
		console_formatter = colorlog.ColoredFormatter(
			console_format_str, 
			reset=True,
			log_colors={
				'DEBUG': 'bold_cyan',
				'INFO': 'bold_green',
				'WARNING': 'bold_yellow',
				'ERROR': 'bold_red',
				'CRITICAL': 'bold_red,bg_white',
			},
			secondary_log_colors={
				'message': {
					'DEBUG': 'white',
					'INFO': 'bold_white',
					'WARNING': 'bold_yellow',
					'ERROR': 'bold_red',
					'CRITICAL': 'bold_red',
				},
			},
			style='%'
		)
		formatter = colorlog.ColoredFormatter(
			file_format_str,
			reset=True,
			log_colors={
				'DEBUG': 'bold_cyan',
				'INFO': 'bold_green',
				'WARNING': 'bold_yellow',
				'ERROR': 'bold_red',
				'CRITICAL': 'bold_red,bg_white',
			},
			secondary_log_colors={
				'message': {
					'DEBUG': 'white',
					'INFO': 'bold_white',
					'WARNING': 'bold_yellow',
					'ERROR': 'bold_red',
					'CRITICAL': 'bold_red',
				},
			},
			style='%'
		)

	if (args.log != "console"):
		file_h.setFormatter(formatter) 
		logger.addHandler(file_h)
	else:
		console_h.setFormatter(console_formatter)
		logger.addHandler(console_h)