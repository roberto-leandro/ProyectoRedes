import threading
import struct
import sys
import readline
import socket
from abc import ABC, abstractmethod


class AbstractNode(ABC):
	HEADER_SIZE = 2
	TRIPLET_SIZE = 8
	SOCKET_TYPE = None 	     # Defined in the subclasses
	NODE_TYPE_STRING = None  # Defined in the subclasses

	def __init__(self, ip, port):
		self.port = port
		self.ip = ip
		self.reachability_table = {}
		self.sock = socket.socket(socket.AF_INET, self.SOCKET_TYPE)
		print(self.NODE_TYPE_STRING)
		print("Address:", ip)
		print("Port:", port)

	def receive_and_decode_message(self, connection):
		# Header is the first 2 bytes, it contains the length
		header = connection.recv(2)
		length = struct.unpack('!H', header)[0]
		print(f"RECEIVED A MESSAGE WITH {length} TRIPLETS:")

		for i in range(0, length):
			# Read each triplet
			message = connection.recv(self.TRIPLET_SIZE)
			triplet = struct.unpack('!BBBBBBBB', message)

			# Get each of the triplet's values
			ip = triplet[:4]
			mask = triplet[4]
			cost = int.from_bytes(triplet[5:], byteorder='big', signed=False)

			print(f"ADDRESS: {ip[0]}.{ip[1]}.{ip[2]}.{ip[3]}", f", SUBNET MASK: {mask}, COST: {cost}")
	
	def start_node(self):
		""" Create two new threads
		one to handle console commands and
		another to listen to incoming connections. """
		print("START EXECUTED")
		connection_handler_thread = threading.Thread(target=self.handle_incoming_connections)
		connection_handler_thread.start()
		self.handle_console_commands()

	@abstractmethod
	def handle_incoming_connections(self):
		pass

	@abstractmethod
	def handle_console_commands(self):
		pass