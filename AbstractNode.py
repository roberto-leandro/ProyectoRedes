import threading
import struct
import sys
import readline
import socket
from abc import ABC, abstractmethod


class AbstractNode(ABC):
    HEADER_SIZE = 2
    TRIPLET_SIZE = 8
    SOCKET_TIMEOUT = 5.0

    # Defined in the subclasses
    SOCKET_TYPE = None
    NODE_TYPE_STRING = None

    def __init__(self, ip, port):
        self.port = port
        self.ip = ip
        self.reachability_table = {}
        # Controls access to the shared table
        self.reachability_table_lock = threading.Lock()
        self.connections = {}
        self.sock = socket.socket(socket.AF_INET, self.SOCKET_TYPE)

        # Will be set to False when the node should be deleted
        self.continue_execution = True
        print(self.NODE_TYPE_STRING)
        print(f"Address: {ip}")
        print(f"Port: {port}")

    def start_node(self):
        """ Create two new threads
        one to handle console commands and
        another to listen to incoming connections. """
        connection_handler_thread = threading.Thread(target=self.handle_incoming_connections)
        connection_handler_thread.start()
        self.handle_console_commands()

    def handle_console_commands(self):
        print("Available commands are:\n    sendMessage <address> <por>\n    deleteNode\n")
        while self.continue_execution:
            command = input("Enter your command...\n> ")
            command = command.strip().split(" ")

            if len(command) == 0:
                print("Please enter a valid command.")

            elif command[0] == "sendMessage":
                message = self.read_and_encode_message()
                self.send_message(ip=command[1], port=int(command[2]), message=message)

            elif command[0] == "exit" or command[0] == "deleteNode":
                self.stop_node()

            elif command[0] == "printTable":
                self.print_reachability_table()

            else:
                print("Unrecognized command, try again.")

    def decode_message(self, message):
        offset = 0
        while offset < len(message):
            # Unpack the binary
            triplet = struct.unpack('!BBBBBBBB', message[offset:offset+8])

            # Get each of the triplet's values
            ip = triplet[:4]
            mask = triplet[4]
            cost = int.from_bytes(triplet[5:], byteorder='big', signed=False)

            offset += self.TRIPLET_SIZE
            print(f"ADDRESS: {ip[0]}.{ip[1]}.{ip[2]}.{ip[3]}", f", SUBNET MASK: {mask}, COST: {cost}")

            # Write to the reachability table, as many threads may perform read/write we need to lock it
            self.reachability_table_lock.acquire()

            if (ip, mask) not in self.reachability_table or self.reachability_table[(ip, mask)] > cost:
                self.reachability_table[(ip, mask)] = cost

            self.reachability_table_lock.release()

    def read_and_encode_message(self):
        length = int(input("Enter the length of your message...\n"))
        message = bytearray(2 + length*self.TRIPLET_SIZE)
        # First encode 2 bytes that represents the message length
        struct.pack_into("!H", message, 0, length)

        offset = 2
        for _ in range(0, length):
            current_message = input("Type the message to be sent as follows:\n" + "<IP address> <subnet mask> <cost>\n")
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

            # Write the cost into the message buffer, copying only 3 bytes and omitting 1
            # The least significant byte is the one omitted because its encoded
            # as big endian
            message[offset+5:offset+8] = cost[1:]

            # Move the offset to write the next triplet
            offset += self.TRIPLET_SIZE

        return message

    def print_reachability_table(self):
        print("Current reachability table:")
        self.reachability_table_lock.acquire()

        if not self.reachability_table:
            print("The reachability table is empty.")

        else:
            for (ip, mask), cost in self.reachability_table.items():
                print(f"Address: {ip[0]}.{ip[1]}.{ip[2]}.{ip[3]}, mask: {mask}, cost: {cost}.")

        self.reachability_table_lock.release()

    # TCPNodes should store the connection, UDPNodes discard it after receiving data.
    @abstractmethod
    def handle_incoming_connections(self):
        pass

    # TCPNodes should try to use an existing connection whenever possible, UDPNodes should create a new connection.
    @abstractmethod
    def send_message(self, ip, port, message):
        pass

    # Each protocol uses a different method in the socket to read data.
    @abstractmethod
    def receive_message(self, connection):
        pass

    # TCPNodes need to close all their sockets, as opposed to UDPNodes.
    @abstractmethod
    def stop_node(self):
        pass