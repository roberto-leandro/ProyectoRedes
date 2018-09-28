import threading
import struct
import socket
from abc import ABC, abstractmethod

try:
    import readline
except ImportError:
    pass

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
        self.sock = socket.socket(socket.AF_INET, self.SOCKET_TYPE)

        # Will be set when the node should be deleted
        self.stopper = threading.Event()
        print(self.NODE_TYPE_STRING)
        print(f"Address: {ip}")
        print(f"Port: {port}")

    def start_node(self):
        """ Create two new threads
        one to handle console commands and
        another to listen to incoming connections. """
        connection_handler_thread = \
            threading.Thread(target=self.handle_incoming_connections)
        connection_handler_thread.start()
        self.handle_console_commands()

    def handle_console_commands(self):
        print("Available commands are:")
        print("    sendMessage <address> <port>")
        print("    deleteNode")
        while not self.stopper.is_set():
            command = input("Enter your command...\n> ")
            command = command.strip().split(" ")

            if len(command) == 0:
                print("Please enter a valid command.")

            elif command[0] == "sendMessage":
                message = self.read_and_encode_message()
                self.send_message(ip=command[1],
                                  port=int(command[2]),
                                  message=message)

            elif command[0] == "exit" or command[0] == "deleteNode":
                self.stop_node()

            elif command[0] == "printTable":
                self.print_reachability_table()

            else:
                print("Unrecognized command, try again.")

    def decode_message(self, message, address):
        offset = 0
        while offset < len(message):
            # Unpack the binary
            triplet = struct.unpack('!BBBBBBBB', message[offset:offset+8])

            # Get each of the triplet's values
            ip = triplet[:4]
            mask = triplet[4]
            cost = int.from_bytes(triplet[5:], byteorder='big', signed=False)

            offset += self.TRIPLET_SIZE
            print(f"ADDRESS: {ip[0]}.{ip[1]}.{ip[2]}.{ip[3]}",
                  f", SUBNET MASK: {mask}, COST: {cost}")

            # Write to the reachability table,
            # as many threads may perform read/write we need to lock it
            self.reachability_table_lock.acquire()

            net_address = (ip, mask)
            if net_address not in self.reachability_table or \
               self.reachability_table[net_address][1] > cost:
                self.reachability_table[net_address] = (address, cost)

            self.reachability_table_lock.release()

    @staticmethod
    def __get_valid_message_input():
        def get_input():
            new_input = input("Type the message to be sent as follows:\n" +
                              "<IP address> <subnet mask> <cost>\n")
            new_input = new_input.strip().split(' ')
            return new_input

        while True:
            message = get_input()
            if len(message) != 3:
                print("Wrong number of tokens, expected 3 tokens with the format:")
                print("x.x.x.x x x     Where x is a positive integer")
                continue

            address_token_list = message[0].strip().split('.')
            try:
                address_token_list = [int(tok) for tok in address_token_list]
                net_mask = int(message[1])
                cost = int(message[2])
            except ValueError:
                print("Unexpected input, expected input with format:")
                print("x.x.x.x x x     Where x is a positive integer")
                continue

            if len(address_token_list) != 4:
                print("Invalid address, expected address with format: x.x.x.x")
                continue

            is_address_valid = True
            for token in address_token_list:
                if token > 255:
                    print("Invalid address token, must be less than 255")
                    is_address_valid = False
                    break
                elif token < 0:
                    print("Invalid address token, must be a positive integer")
                    is_address_valid = False
                    break
            if not is_address_valid:
                continue

            if net_mask > 32:
                print("Invalid network mask, expected less than 32")
                continue
            elif net_mask < 0:
                print("Network mask must be a positive integer")
                continue

            if cost < 0:
                print("Invalid cost, must be a positive integer")
                continue
            elif cost > 0xFF_FF_FF:  # max three bytes
                print("Invalid cost, max number exceeded")
                continue

            return address_token_list, net_mask, cost

    def read_and_encode_message(self):
        length = 0
        while not length > 0:
            try:
                length = int(input("Enter the length of your message...\n"))
            except ValueError:
                print("Please enter a valid integer.")

        message = bytearray(2 + length*self.TRIPLET_SIZE)
        # First encode 2 bytes that represents the message length
        struct.pack_into("!H", message, 0, length)

        offset = 2
        for _ in range(0, length):
            address, net_mask, cost = self.__get_valid_message_input()

            # Each triplet is encoded with the following 8-byte format:
            # BBBB (4 bytes) network address
            #  B   (1 byte)  subnet mask
            #  I   (4 bytes) cost.
            #      The cost should only be 3 bytes, this is handled below.
            struct.pack_into('!BBBBB', message, offset,
                             address[0], address[1],
                             address[2], address[3],
                             net_mask)

            # Pack the cost into a 4 byte buffer
            cost_bytes = struct.pack('!I', cost)

            # Write the cost into the message buffer, copying only 3 bytes and omitting 1
            # The least significant byte is the one omitted because its encoded
            # as big endian
            message[offset+5:offset+8] = cost_bytes[1:]

            # Move the offset to write the next triplet
            offset += self.TRIPLET_SIZE

        return message

    def print_reachability_table(self):
        print("Current reachability table:")
        self.reachability_table_lock.acquire()

        if not self.reachability_table:
            print("The reachability table is empty.")

        else:
            for (ip, mask), (address, cost) in self.reachability_table.items():
                print(f"Address: {ip[0]}.{ip[1]}.{ip[2]}.{ip[3]},",
                      f"mask: {mask}, address: {address}, {cost}.")
                print(address, cost)

        self.reachability_table_lock.release()

    # TCPNodes should store the connection, UDPNodes discard it after receiving data.
    @abstractmethod
    def handle_incoming_connections(self):
        pass

    # TCPNodes should try to use an existing connection whenever possible,
    # UDPNodes should create a new connection.
    @abstractmethod
    def send_message(self, ip, port, message):
        pass

    # Each protocol uses a different method in the socket to read data.
    @abstractmethod
    def receive_message(self, connection, address):
        pass

    # TCPNodes need to close all their sockets, as opposed to UDPNodes.
    @abstractmethod
    def stop_node(self):
        pass
