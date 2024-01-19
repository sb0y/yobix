import os

class Whitelist(object):
	zones = ()
	def __init__(self, wl_path) -> None:
		if not os.path.isfile(wl_path):
			raise FileNotFoundError("no file '%s'" % wl_path)

		with open(wl_path, 'r') as f:
			self.zones = tuple(f.read().splitlines(keepends=False))