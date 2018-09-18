import threading
import struct
import sys
import readline
import socket
from AbstractNode import AbstractNode


class TCPNode(AbstractNode):
	SOCKET_TYPE = socket.SOCK_STREAM 		
	NODE_TYPE_STRING = "[PseudoBGP Node]"





	def handle_incoming_connections(self):
		print("LISTENING TO INCOMING CONNECTIONS")
		self.sock.bind((self.ip, self.port))
		self.sock.listen(self.port)

		while True:
			conn, addr = self.sock.accept()
			print(f"CONNECTED WITH {addr}")
			with conn:
				self.receive_and_decode_message(conn)

	def send_message(self, ip, port, message):
		print("SENDING ", len(message), " BYTES TO ", ip, ":", port)
		with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as host_socket:
			host_socket.connect((ip, port))
			host_socket.sendall(message)

	def handle_console_commands(self):
		while True:
			command = input("Enter your command...\n> ")
			command = command.strip().split(" ")

			if command[0] == "sendMessage":
				message = self.read_message()
				self.send_message(ip=command[1], port=int(command[2]), message=message)
			elif command[0] == "exit":
				sys.exit(1)

	def stop_node(self):
		# TODO
		# Close all open connections and terminate all threads
		pass

	def read_message(self):
		length = int(input("Enter the length of your message...\n"))
		message = bytearray(2 + length*self.TRIPLET_SIZE)
		# First encode 2 bytes that represents the message length
		struct.pack_into("!H", message, 0, length)

		offset = 2
		for i in range(0, length):
			current_message =  input(f"Type the message to be sent as follows:\n" + f"<IP address> <subnet mask> <cost>\n")
			current_message = current_message.strip().split(' ')
			address = current_message[0].strip().split('.')

			# Each triplet is encoded with the following 8-byte format:
			# BBBB (4 bytes) network address
			#  B   (1 byte)  subnet mask
			#  I   (4 bytes) cost.
			#      The cost should only be 3 bytes, this is handled below.
			struct.pack_into('!BBBBB', message, offset,
							int(address[0]), int(address[1]),
							int(address[2]), int(address[3]),
							int(current_message[1]))

			# Pack the cost into a 4 byte buffer
			cost = struct.pack('!I', int(current_message[2]))

			# Write the cost into the message buffer, copying only 3 bytes
			# The least significant byte is the one dropped because its encoded
			# as big endian
			message[offset+5:offset+8] = cost[1:]

			# Move the offset to write the next triplet
			offset += self.TRIPLET_SIZE

		return message


if __name__ == "__main__":
	if len(sys.argv) != 3:
		print(sys.argv)
		print(len(sys.argv))
		print("Incorrect arg number")
		sys.exit(1)

	node = TCPNode(sys.argv[1], int(sys.argv[2]))
	node.start_node()
