import os
import configparser

class Config(object):
	proxies = []
	config = configparser.ConfigParser(interpolation=None)
	def __init__(self, conf_path) -> None:
		if not os.path.isfile(conf_path):
			raise FileNotFoundError("no config file '%s'" % conf_path)
		self.config.read(conf_path)
		self.build_proxies_list()

	def get(self, key, section="general", fallback=None):
		return self.config.get(section, key, fallback=fallback)

	def get_int(self, key, section="general", fallback=None):
		return int(self.get(key, section, fallback))

	def build_proxies_list(self) -> list:
		enabled = self.config.get("socks proxies", "enabled", fallback="").split(',')
		for section in enabled:
			section = section.strip()
			if self.config.has_section(section):
				proxy = dict(self.config.items(section))
				self.proxies.append(proxy)
