import multiprocessing
import dns.name
import dns.query
import dns.resolver
import logging

logger = logging.getLogger(__name__)

class Resolver(multiprocessing.Process):
	config = None
	zones_data = {}
	ips_to_zones = {}
	zones = ()
	event = multiprocessing.Event()

	def __init__(self, config, zones: tuple) -> None:
		super(Resolver, self).__init__()
		self.config = config
		self.zones = zones
		self.update_zones()

	def __del__(self) -> None:
		self.join()

	def run(self) -> None:
		logger.info("Starting DNS refresher process ...")
		wakeup_time = self.count_min_ttl() - 180
		#wakeup_time = 15
		logger.debug("Wakeup time is '%d'", wakeup_time)
		while not self.event.wait(wakeup_time):
			logger.info("Updateing zones informaion ...")
			self.update_zones()

	def count_min_ttl(self) -> int:
		ttls = []
		for zone, data in self.zones_data.items():
			ttls.append(data["ttl"])

		return min(ttls)

	def update_zones(self) -> None:
		zones_new = {}
		ips_to_zones_new = {}
		for zone in self.zones:
			logger.debug("Processing zone '%s' ...", zone)
			nss = self.get_authoritative_nameserver(zone)
			if nss:
				result = self.get_ip_from_nss(zone, nss)
				zones_new[zone] = result
		for zone, data in zones_new.items():
			for ip in data["ips"]:
				ips_to_zones_new[ip] = {"ips": data["ips"], "zone": zone, "ttl": data["ttl"]}

		self.zones_data = zones_new
		self.ips_to_zones = ips_to_zones_new

	def get_authoritative_nameserver(self, zone: str) -> str:
		n = dns.name.from_text(zone)

		depth = 3
		default = dns.resolver.get_default_resolver()
		nameserver = default.nameservers[0]
		nameservers = []

		last = False
		while not last:
			s = n.split(depth)

			last = s[0].to_unicode() == u'@'
			sub = s[1]

			logger.info("Looking up '%s' on '%s'", sub, nameserver)
			query = dns.message.make_query(sub, dns.rdatatype.NS)
			response = dns.query.udp(query, nameserver)

			rcode = response.rcode()
			if rcode != dns.rcode.NOERROR:
				if rcode == dns.rcode.NXDOMAIN:
					raise Exception("'%s' does not exist" % sub)
				else:
					raise Exception('Error %s' % dns.rcode.to_text(rcode))

			rrset = None
			if len(response.authority) > 0:
				rrset = response.authority[0]
			else:
				rrset = response.answer[0]

			if last:
				for rr in rrset:
					if rr.rdtype == dns.rdatatype.SOA:
						logger.info("Same server is authoritative for '%s'", sub)
					else:
						authority = rr.target
						logger.info("'%s' is authoritative for '%s'", authority, sub)
						try:
							ns = default.resolve(authority).rrset[0].to_text()
							#print(ns)
							nameservers.append(ns)
						except Exception as e:
							logger.error("Error occurred while authority IP fetching!")
							logger.exception(e)

			depth += 1

		return nameservers

	def get_ip_from_nss(self, zone: str, nss: list) -> dict:
		logger.info("Trying to fetch IP with original TTL from '%s' NSs ...", nss)
		ips = []; ttl = 0;
		try:
			resolver = dns.resolver.Resolver()
			resolver.nameservers = nss
			resolver.timeout = self.config.get_int("dns_timeout", "resolver", fallback=5)
			resolver.lifetime = self.config.get_int("dns_lifetime", "resolver", fallback=5)
			answers = resolver.query(zone)
			ttl = answers.rrset.ttl
			ips = list(i.to_text() for i in answers)
		except Exception as e:
			logger.error("Error occurred while fetching IP from NS!")
			logger.exception(e)

		logger.debug("ips = %s, ttl = %d", ips, ttl)
		
		return {"ips": ips, "ttl": ttl}


