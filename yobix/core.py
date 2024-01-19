import socket, select, struct, errno
import socks
import time
import logging

logger = logging.getLogger(__name__)

SO_ORIGINAL_DST = 80
# 2^14
BYTES_BUF_SIZE = 16384

class Core(object):
	config = None
	running = True
	resolver = None
	channels = {}
	connections = {}
	buffers = {}
	connect_errnos = {}

	def __init__(self, config, resolver) -> None:
		self.config = config
		self.resolver = resolver
		self.proxy_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.proxy_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		self.proxy_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
		self.proxy_socket.bind((config.get("listen", fallback="0.0.0.0"), config.get_int("port", fallback=10111)))
		self.proxy_socket.setblocking(False)
		self.proxy_socket.listen(5)

		self.epoll = select.epoll()
		#  | select.EPOLLOUT | select.EPOLLHUP | select.EPOLLRDHUP | select.EPOLLERR
		self.epoll.register(self.proxy_socket.fileno(), select.EPOLLIN)

	def stop(self) -> None:
		self.running = False
		for i in self.connections:
			self.connections[i].close()

		#self.finalize()

	def finalize(self) -> None:
		if self.proxy_socket.fileno() > 0:
			self.epoll.unregister(self.proxy_socket.fileno())
		self.epoll.close()
		self.shutdown_socket(self.proxy_socket)
		self.proxy_socket.close()

	def shutdown_socket(self, so: socket) -> None:
		try:
			#if len(so.recv(2, socket.MSG_PEEK)) <= 0:
			so.shutdown(socket.SHUT_RDWR)
		except OSError as e:
			logger.warning("Failed to shutdown socket!")
			if e.errno != 107:
				logger.exception(e)

	def send(self, so: socket, buffer: bytes, fileno: int=None) -> int:
		byteswritten = -1
		try:
			byteswritten = so.send(buffer)
		except BlockingIOError as e:
			logger.warning("send(): BlockingIOError!")
			logger.exception(e)
			#self.epoll.modify(fileno, 0)
			#self.shutdown_socket(self.channels[fileno])
		except ConnectionResetError as e:
			logger.warning("send(): ConnectionResetError!")
			logger.exception(e)
			if fileno is not None:
				self.epoll.modify(fileno, 0)
				self.shutdown_socket(so)
		except BrokenPipeError as e:
			logger.warning("send(): BrokenPipeError!")
			logger.exception(e)
			if fileno is not None:
				self.epoll.modify(fileno, 0)
				self.shutdown_socket(so)

		return byteswritten

	def recv(self, so: socket, fileno: int=None, rlen: int=BYTES_BUF_SIZE) -> bytes:
		data = b''
		try:
			data = so.recv(rlen)
		except BlockingIOError as e:
			logger.warning("recv(): BlockingIOError!")
			logger.exception(e)
			#self.epoll.modify(fileno, 0)
			#self.shutdown_socket(self.channels[fileno])
		except ConnectionResetError as e:
			logger.warning("recv(): ConnectionResetError!")
			logger.exception(e)
			if fileno is not None:
				self.epoll.modify(fileno, 0)
				#so.close()
				#self.shutdown_socket(so)
		except BrokenPipeError as e:
			logger.warning("recv(): BrokenPipeError!")
			logger.exception(e)
			if fileno is not None:
				self.epoll.modify(fileno, 0)
				self.shutdown_socket(so)

		return data

	def accept_new_client(self) -> None:
		"""Try to connect to the target and when this succeeds, accept the
		client connection.  Keep track of both and their connections
		"""
		target = None
		connection, address = self.proxy_socket.accept()
		try:
			odestdata = connection.getsockopt(socket.SOL_IP, SO_ORIGINAL_DST, 16)
			_, port_dst, a1, a2, a3, a4 = struct.unpack("!HHBBBBxxxxxxxx", odestdata)
			address_dst = "%d.%d.%d.%d" % (a1, a2, a3, a4)
			
			if address_dst in self.resolver.ips_to_zones:
				logger.debug("Whitelisted IP! Creating proxy connection ...")
				target = socks.socksocket()
				target.set_proxy(proxy_type=socks.PROXY_TYPE_SOCKS5, addr=self.config.proxies[0]["host"], port=int(self.config.proxies[0]["port"]))
			else:
				logger.debug("IP is not in whitelist. Using plain socket ...")
				target = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

			#target.settimeout(10.0)
			target.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
			target.setblocking(0)

			logger.debug("Connection to '%s:%d'", address_dst, port_dst)
			target.connect_ex((address_dst, port_dst))
			#target.setblocking(False)
		except (socket.error, socks.ProxyConnectionError) as e:
			if e.errno != errno.EINPROGRESS:
				logger.error("An error occured while target connect!")
				logger.exception(e)
				target = None

		if target:
			self.epoll.register(connection.fileno(), select.EPOLLIN | select.EPOLLHUP | select.EPOLLERR | select.EPOLLRDHUP | select.EPOLLPRI)
			#select.EPOLLERR | select.EPOLLEXCLUSIVE | select.EPOLLET | select.EPOLLHUP | select.EPOLLIN | select.EPOLLMSG | select.EPOLLONESHOT | select.EPOLLOUT | select.EPOLLPRI | select.EPOLLRDBAND | select.EPOLLRDHUP | select.EPOLLRDNORM | select.EPOLLWRBAND | select.EPOLLWRNORM | select.EPOLL_RDHUP | select.EPOLL_CLOEXEC
			self.epoll.register(target.fileno(), select.EPOLLIN | select.EPOLLOUT | select.EPOLLERR | select.EPOLLHUP | select.EPOLLRDHUP | select.EPOLLRDBAND | select.EPOLLWRBAND | select.EPOLLPRI)

			# save the sockets for the target and client
			self.connections[connection.fileno()] = connection
			self.connections[target.fileno()] = target

			# save the sockets but point them to each other
			self.channels[connection.fileno()] = target
			self.channels[target.fileno()] = connection

			self.buffers[connection.fileno()] = b''
			self.buffers[target.fileno()] = b''
		else:
			self.send(so=connection, buffer=bytes("Can't connect to {}\n".format(address), 'UTF-8'))
			connection.close()

	def send_buffer(self, fileno: int) -> None:
		byteswritten = self.send(so=self.channels[fileno], buffer=self.buffers[fileno], fileno=fileno)
		bufflen = len(self.buffers[fileno])
		if bufflen > byteswritten:
			self.buffers[fileno] = self.buffers[fileno][byteswritten:]
			self.epoll.modify(fileno, select.EPOLLOUT)

	def relay_data(self, fileno: int) -> None:
		"""Receive a chunk of data on fileno and relay that data to its
		corresponding target socket. Spill over to buffers what can't be sent
		"""
		data = b''
		try:
			data = self.recv(so=self.connections[fileno], fileno=fileno)
		except (socket.error, socks.ProxyConnectionError):
			self.epoll.modify(fileno, 0)
			return
		if len(data) == 0:
			if self.connections[fileno].fileno() > 0:
				#self.connections[fileno].setsockopt(socket.IPPROTO_TCP, socket.TCP_CORK, 0)
				# peer closed connection, shut down socket and
				# wait for EPOLLHUP to clean internal structures
				self.epoll.modify(fileno, 0)

				self.shutdown_socket(self.connections[fileno])
		else:
			# if there's already something in the send queue, add to it
			if len(self.buffers[fileno]) > 0:
				self.buffers[fileno] += data
			else:
				try:
					byteswritten = self.send(so=self.channels[fileno], buffer=data, fileno=fileno)
					if len(data) > byteswritten:
						self.buffers[fileno] = data[byteswritten:]
						self.epoll.modify(fileno, select.EPOLLOUT)
						#self.connections[fileno].setsockopt(socket.IPPROTO_TCP, socket.TCP_CORK, 1)
				except (socket.error, socks.ProxyConnectionError) as e:
					if e.errno != errno.EINPROGRESS:
						self.send(so=self.connections[fileno], buffer=bytes("Can't reach server\n", 'UTF-8'))
						self.epoll.modify(fileno, 0)
						self.shutdown_socket(self.connections[fileno])
						#self.connections[fileno].setsockopt(socket.IPPROTO_TCP, socket.TCP_CORK, 0)

	def close_channels(self, fileno: int) -> None:
		"""Close the socket and its corresponding target socket and stop
		listening for them"""
		out_fileno = self.channels[fileno].fileno()
		if out_fileno <= 0 or fileno <= 0:
			return

		self.epoll.unregister(fileno)

		#logger.debug(self.channels)
		#logger.debug(self.connections)

		# close and delete both ends
		self.channels[out_fileno].close()
		self.channels[fileno].close()
		del self.channels[out_fileno]
		del self.channels[fileno]
		del self.connections[out_fileno]
		del self.connections[fileno]

		#logger.debug(self.channels)
		#logger.debug(self.connections)

	def run(self) -> None:
		try:
			while self.running:
				if not self.running:
					break
				events = self.epoll.poll(timeout=1, maxevents=-1)
				for fileno, event in events:
					if fileno == self.proxy_socket.fileno():
						self.accept_new_client()
					elif event & select.EPOLLIN:
						try:
							self.channels[fileno].getpeername()
							self.connections[fileno].getpeername()
						except OSError as e:
							if e.errno == 107:
								break
						en = self.connections[fileno].getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
						if en == 0: #
							self.relay_data(fileno=fileno)
					elif event & select.EPOLLOUT:
						try:
							self.channels[fileno].getpeername()
							self.connections[fileno].getpeername()
						except OSError as e:
							if e.errno == 107:
								break
						en = self.connections[fileno].getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
						if en == 0: #
							self.send_buffer(fileno=fileno)
					elif event & (select.EPOLLERR | select.EPOLLHUP | select.EPOLLRDHUP):
						logger.debug("HUP!")
						self.close_channels(fileno=fileno)
						break
				#time.sleep(0.1)
		finally:
			self.finalize()