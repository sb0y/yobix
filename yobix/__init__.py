import signal
from argparse import ArgumentParser
import argcomplete
import logging

from yobix.core import Core
from yobix.dns import Resolver
from yobix.whitelist import Whitelist
from yobix.log import init_log
from yobix.config import Config
from yobix.__version__ import __version__

logger = logging.getLogger(__name__)

def build_argparser():
	parser = ArgumentParser(prog="yobix", description="Transparent Proxy with TCP SOCKS5 traffic routing",
							epilog=("Examples: yobix -c /etc/yobix/yobix.conf"))

	general = parser.add_argument_group('General')
	general.add_argument('-c', '--config', metavar="PATH", default='/etc/yobix/yobix.conf',
						 help="(optional) Path to configuration file "
						 "('/etc/yobix/yobix.conf', default)")
	general.add_argument('-w', '--whitelist', metavar="PATH", default="/etc/youbix/whitelist.txt",
						 help="(optional) Whitelist with domains to bypass")
	general.add_argument('-l', '--log', metavar="PATH",
						 help="(optional) Path to log file "
						 "('console' logs to console, default)")
	general.add_argument('-v', '--verbose', action='store_true',
						 help="(optional) Logging in INFO mode")
	general.add_argument('-V', '--very_verbose', action='store_true',
						 help="(optional) Logging in DEBUG mode")

	argcomplete.autocomplete(parser)
	return parser

def main():
	args = build_argparser().parse_args()
	config = Config(args.config)
	if not args.log:
		args.log = config.get("log_output", fallback="console")
	if not args.whitelist:
		args.whitelist = config.get("whitelist", fallback="/etc/yobix/whitelist.txt")
	args.log_level = config.get("log_level", fallback="error").lower()
	init_log(args)
	logger.info("Started Yobix version '%s'", __version__)
	logger.info("Initiliazion Yobix DNS zones for redirect ...")
	resolver_thread = Resolver(config, Whitelist(args.whitelist).zones)
	resolver_thread.start()
	app = Core(config, resolver_thread)
	def signal_handler(sig, frame):
		logger.info('Caught signal: %d', sig)
		if sig in (signal.SIGTERM, signal.SIGINT):
			app.stop()
			resolver_thread.event.clear()
		elif sig == signal.SIGPIPE:
			return
		else:
			try:
				raise SystemExit
			finally:
				logging.info("Yobix version %s successfully terminated", __version__)
				print("Goodbye!")

	signal.signal(signal.SIGTERM, signal_handler)
	signal.signal(signal.SIGINT,  signal_handler)

	logger.info("Starting packages redirect ...")
	app.run()