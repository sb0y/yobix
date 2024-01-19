#!/usr/bin/env python3

import socket, select
import struct
import socks

if __name__ == '__main__':

	SO_ORIGINAL_DST = 80

	serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	serversocket.bind(('0.0.0.0', 10111))
	serversocket.listen(1)
	serversocket.setblocking(0)
	target_fileno = None
	clientsocket = None
	
	epoll = select.epoll()
	epoll.register(serversocket.fileno(), select.EPOLLIN | select.EPOLLOUT) # ???

	try:
		all_rec = False; all_sent = False;
		connections = {"server": {}, "target": {}}; requests = {"server": {}, "target": {}}; responses = {"server": {}, "target": {}};
		while True:
			events = epoll.poll(1)
			for fileno, event in events:
				if fileno == serversocket.fileno():
					print("accept")
					connection, address = serversocket.accept()
					connection.setblocking(0)
					epoll.register(connection.fileno(), select.EPOLLIN | select.EPOLLOUT)
					connections["server"][connection.fileno()] = connection
					requests["server"][connection.fileno()] = b''
					responses["server"][connection.fileno()] = b''

					#get the original dst address and port
					odestdata = connection.getsockopt(socket.SOL_IP, SO_ORIGINAL_DST, 16)
					_, port_dst, a1, a2, a3, a4 = struct.unpack("!HHBBBBxxxxxxxx", odestdata)
					address_dst = "%d.%d.%d.%d" % (a1, a2, a3, a4)
						
					#clientsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
					clientsocket = socks.socksocket()
					clientsocket.set_proxy(proxy_type=socks.PROXY_TYPE_SOCKS5, addr="62.113.115.94", port=16072)
					clientsocket.connect((address_dst, port_dst))
					clientsocket.setblocking(0)
					target_fileno = clientsocket.fileno()

					connections["target"][clientsocket.fileno()] = clientsocket
					requests["target"][clientsocket.fileno()] = b''
					responses["target"][clientsocket.fileno()] = b''

					epoll.register(clientsocket.fileno(), select.EPOLLOUT | select.EPOLLIN)

					all_sent = False
					all_rec = False

					print("connected to %s:%d" % (address_dst, port_dst))
					print(socket.getfqdn(address_dst))
					#epoll.modify(connection.fileno(), select.EPOLLIN)
				
				# server read
				# accept_connect
				elif fileno in connections["server"] and event & select.EPOLLIN and all_rec == False:
					#print("server_read")
					data = connections["server"][fileno].recv(8064)
					if data:
						requests["server"][fileno] += data
					#else:
					#	all_rec = True
					#connections[fileno].setsockopt(socket.IPPROTO_TCP, socket.TCP_CORK, 1)
					#print('-'*40 + '\n' + requests["server"][fileno].decode())
					#epoll.modify(clientsocket.fileno(), select.EPOLLIN)

				# to target write
				elif fileno in connections["target"] and event & select.EPOLLOUT and len(requests["server"][connection.fileno()]) > 0:
					print("client_write")
					byteswritten = connections["target"][target_fileno].send(requests["server"][connection.fileno()])
					print(requests["server"][connection.fileno()])
					requests["server"][connection.fileno()] = requests["server"][connection.fileno()][byteswritten:]
					#epoll.modify(connection.fileno(), select.EPOLLIN)
					#epoll.modify(clientsocket.fileno(), select.EPOLLIN)
					print("write end")

				# read from target
				elif fileno in connections["target"] and event & select.EPOLLIN:
					print("client_read")
					#connections[fileno].setsockopt(socket.IPPROTO_TCP, socket.TCP_CORK, 1)
					data = clientsocket.recv(8064)
					print(data)
					if data:
						responses["target"][fileno] += data
					else:
						all_sent = True
					#print(responses["target"][fileno])

				# server write to client
				elif target_fileno and fileno in connections["server"] and event & select.EPOLLOUT and len(responses["target"][target_fileno]) > 0:
					print("server_write")
					byteswritten = connection.send(responses["target"][target_fileno])
					responses["target"][target_fileno] = responses["target"][target_fileno][byteswritten:]

				#if event & select.EPOLLHUP or event & select.EPOLLRDHUP or event & select.EPOLLERR:
				#	print("HUP")
				#	if target_fileno in connections["target"]:
				#		del connections["target"][target_fileno]
				#		epoll.unregister(target_fileno)
				#		clientsocket.close()
				#	epoll.modify(connection.fileno(), select.EPOLLIN)

				#if all_rec:
					#print("goodbye socket!")
					#if target_fileno in connections["target"]:
					#	del connections["target"][target_fileno]

					#if clientsocket:
					#	clientsocket.close()
					#target_fileno = None
					#all_rec = False
					#lientsocket = None

	finally:
		epoll.unregister(serversocket.fileno())
		#epoll.unregister(clientsocket.fileno())
		epoll.close()
		for i in connections["server"]:
			connections["server"][i].close()
		for i in connections["target"]:
			connections["target"][i].close()