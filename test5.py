#!/usr/bin/env python3

import socket, select
import struct

buf = b'GET / HTTP/1.1\r\nHost: ifconfig.me\r\nUser-Agent: curl/7.77.0\r\nAccept: */*\r\n\r\n'

clientsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
clientsocket.connect(('ifconfig.me', 80))
#clientsocket.setblocking(0)

clientsocket.send(buf)
print(clientsocket.recv(1024).decode())