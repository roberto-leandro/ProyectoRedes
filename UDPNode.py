#!/usr/bin/env python3
import sys
import time
import struct
import socket
import selectors
import threading
from AbstractNode import AbstractNode

# Message types
PKT_TYPE_UPDATE         = 1
PKT_TYPE_KEEP_ALIVE     = 2
PKT_TYPE_ACK_KEEP_ALIVE = 3
PKT_TYPE_FLOOD          = 4
PKT_TYPE_DATA_MSG       = 5
PKT_TYPE_COST_CHANGE    = 6
PKT_TYPE_DEAD           = 7

# Hops executed during a flood
HOP_NUMBER = 50
SKIPPED_UPDATES_AFTER_FLOOD = 3

# Data size definitions in bytes
TUPLE_COUNT_SIZE      = 2
TUPLE_SIZE            = 10
PKT_TYPE_SIZE         = 2
BUFFER_SIZE = 2048  # Will be used when reading from a socket TODO reads from the socket should be dynamic

# Various timeouts
SELECTOR_TIMEOUT = .5
SOCKET_TIMEOUT = 5.0

# Time intervals in seconds
SEND_TABLE_UPDATE_INTERVAL = 20
SEND_KEEP_ALIVE_INTERVAL = 20

class UDPNode:

    def __init__(self, ip, mask, port, neighbors):
        # Simple data
        self.port = port
        self.ip = ip
        self.mask = mask
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.ip, self.port))
        self.sock.setblocking(False) #TODO should be true

        self.updates_to_ignore = 0

        # Structures
        # Reachability table: ip, port : mask, (ip, port), cost
        self.reachability_table = {}
        # Neighbors: ip, port : mask, cost, Timer obj, current_retries (0 if node is dead)
        self.neighbors = {}
        # Keep alive acks: ip, port :
        for (n_ip, n_mask, n_port), n_cost in neighbors.items():
            self.neighbors[(n_ip, n_port)] = (n_mask, n_cost)
            self.reachability_table[(n_ip, n_port)] = (n_mask, (n_ip, n_port), n_cost)  # FIXME should not be filled yet

        # Locks
        self.reachability_table_lock = threading.Lock()

        # Events
        self.stopper = threading.Event()
        self.neighbors_lock = threading.Lock()

        # Prints identifying the node
        print(f"Address: {ip}")
        print(f"Port: {port}")
        print(f"Mask: {mask}")
        self.print_neighbors_table()
        self.print_reachability_table()

    def start_node(self):
        connection_handler_thread = threading.Thread(target=self.handle_incoming_connections)
        connection_handler_thread.start()

        while not self.stopper.wait(SEND_TABLE_UPDATE_INTERVAL):
            for (ip, port) in self.neighbors:
                self.send_reachability_table(ip, port)
        print("Finished the update sending loop!")

    def send_keep_alive(self):
        while not self.stopper.wait(SEND_KEEP_ALIVE_INTERVAL):
            for (ip, port) in self.neighbors:
                self.send_keep_alive(ip, port)
        print("Finished the send keep alive loop!")

    def handle_incoming_connections(self):
        main_selector = selectors.DefaultSelector()
        main_selector.register(self.sock, selectors.EVENT_READ)

        while not self.stopper.is_set():
            events = main_selector.select(SELECTOR_TIMEOUT)
            for _ in events:
                if self.stopper.is_set():
                    break
                self.receive_message(self.sock)
        print("Finished the handle incoming connections loop!")

    def receive_message(self, connection):
        # Read enough bytes for the message, a standard packet does not exceed 1500 bytes
        message, address = connection.recvfrom(BUFFER_SIZE)
        print(f"MESSAGE: Connected with {address}")

        message_type = int.from_bytes(message[0:PKT_TYPE_SIZE], byteorder='big', signed=False)

        if message_type == PKT_TYPE_UPDATE:
            if self.updates_to_ignore > 0:
                self.updates_to_ignore -= 1
                return
            tuple_count = struct.unpack('!H', message[PKT_TYPE_SIZE:PKT_TYPE_SIZE + 2])[0]
            print(f"MESSAGE: Received of type UPDATE of size {len(message)} with {tuple_count} tuples.")
            # Decode the received tuples and update the reachability table if necessary
            self.decode_tuples(message[PKT_TYPE_SIZE + TUPLE_COUNT_SIZE:], address)

        elif message_type == PKT_TYPE_KEEP_ALIVE:
            print("MESSAGE: Received of type KEEP_ALIVE")
            self.send_ack_keep_alive(address[0], address[1])
        elif message_type == PKT_TYPE_FLOOD:
            hops = struct.unpack("!B", message[1:2])[0]
            print(f"MESSAGE: Received of type FLOOD: with {hops} hops")
            print("UPDATE: Flushing reachability table")
            with self.reachability_table_lock:
                self.reachability_table.clear()
            self.send_flood_message(hops - 1)
            self.updates_to_ignore = SKIPPED_UPDATES_AFTER_FLOOD + 1

        if self.updates_to_ignore > 0:
            self.updates_to_ignore -= 1
        # TODO: handle all the other cases

    def send_message(self, ip, port, message):
        print(f"MESSAGE: Sending {len(message)} bytes to {ip}:{port}")
        self.sock.sendto(message, (ip, port))

    def send_reachability_table(self, ip, port):
        self.reachability_table_lock.acquire()
        table_size = len(self.reachability_table)
        encoded_message = bytearray(PKT_TYPE_SIZE + TUPLE_COUNT_SIZE + TUPLE_SIZE * table_size)

        # 2 bytes for the message type
        struct.pack_into("!H", encoded_message, 0, PKT_TYPE_UPDATE)

        # 2 bytes for the amount of tuples
        struct.pack_into("!H", encoded_message, PKT_TYPE_SIZE, table_size)

        # Iterate the reachability table, writing each tuple to the encoded_message buffer
        offset = PKT_TYPE_SIZE + TUPLE_COUNT_SIZE  # will to the next empty space in the buffer
        for (r_ip, r_port), (r_mask, _, r_cost) in self.reachability_table.items():
            ip_tuple = tuple([int(tok) for tok in r_ip.split('.')])
            encoded_message[offset:offset + TUPLE_SIZE] = self.encode_tuple(ip_tuple, r_port, r_mask, r_cost)
            offset += TUPLE_SIZE
        self.reachability_table_lock.release()
        if table_size > 0:
            self.send_message(ip, port, encoded_message)

    def encode_tuple(self, ip, port, net_mask, cost):
        message = bytearray(TUPLE_SIZE)
        # Each tuple is encoded with the following 10-byte format:
        # BBBB (4 bytes) ip address (one B byte for each integer in the address)
        #  B   (1 byte)  subnet mask
        #  H   (2 bytes) port
        #  I   (4 bytes) cost
        #      The cost should only be 3 (not 4) bytes, this is handled below.
        struct.pack_into('!BBBBBH', message, 0,
                         ip[0], ip[1],
                         ip[2], ip[3],
                         net_mask, port)

        # Pack the cost into a 4 byte buffer
        cost_bytes = struct.pack('!I', cost)

        # Write the cost into the message buffer, copying only 3 bytes and omitting 1
        # The least significant byte is the one omitted because its encoded as big endian
        message[7:] = cost_bytes[1:]

        return message

    def decode_tuples(self, message, origin_node):
        offset = 0
        tuple_bytes = bytearray(10)
        while offset < len(message):
            # Unpack the binary
            tuple_bytes = struct.unpack('!BBBBBBBBBB', message[offset:offset + TUPLE_SIZE])

            # Get each of the triplet's values
            ip_bytes = tuple_bytes[:4]
            ip = f"{ip_bytes[0]}.{ip_bytes[1]}.{ip_bytes[2]}.{ip_bytes[3]}"
            mask = tuple_bytes[4]
            port = int.from_bytes(tuple_bytes[5:7], byteorder='big', signed=False)
            cost = int.from_bytes(tuple_bytes[7:], byteorder='big', signed=False)

            offset += TUPLE_SIZE
            print(f"ADDRESS: {ip}" +
                  f", SUBNET MASK: {mask}, COST: {cost}")

            self.update_reachability_table(ip, port, mask, cost, origin_node)

    def update_reachability_table(self, ip, port, mask, cost, through_node):
        with self.neighbors_lock:
            total_cost = cost + self.neighbors[through_node][1]

        # Write to the reachability table,
        # as many threads may perform read/write we need to lock it
        with self.reachability_table_lock:
            if (ip, port) not in self.reachability_table or self.reachability_table[(ip, port)][2] > total_cost:
                self.reachability_table[(ip, port)] = (mask, through_node, total_cost)

    def disconnect_address(self, ip, port):
        with self.reachability_table_lock:
            del self.reachability_table[(ip, port)]
        print(f"DISCONNECT: Deleted {ip}:{port} from the reachability table.")

    def send_flood_message(self, hops):
        message = bytearray(2)
        struct.pack_into("!B", message, 0, PKT_TYPE_FLOOD)
        struct.pack_into("!B", message, 1, hops)
        for ip, port in self.neighbors:
            self.send_message(ip, port, message)

    def send_ack_keep_alive(self, ip, port):
        message = bytearray(1)
        struct.pack_into("!B", message, 0, PKT_TYPE_ACK_KEEP_ALIVE)
        self.send_message(ip, port, message)

    def send_keep_alive(self, ip, port):
        message = bytearray(1)
        struct.pack_into("!B", message, 0, PKT_TYPE_KEEP_ALIVE)
        self.send_message(ip, port, message)

    def stop_node(self):
        print("EXIT: Sending close message")

        # Set this flag to false, stopping all loops
        self.stopper.set()

        self.reachability_table_lock.acquire()
        for _, value in self.reachability_table.items():
            address = value[0]
            close_message = struct.pack("!H", 0)
            self.sock.sendto(close_message, address)
        self.reachability_table_lock.release()

    def print_reachability_table(self):
        print("Current reachability table:")
        self.reachability_table_lock.acquire()

        if not self.reachability_table:
            print("The reachability table is empty.")

        else:
            for (ip, port), (mask, (ip2, port2), cost) in self.reachability_table.items():
                print(f"Destiny: {ip}:{port}/{mask},",
                      f"through: {ip2}:{port2}, cost: {cost}.")

        self.reachability_table_lock.release()

    def print_neighbors_table(self):
        print("Neighbors:")
        self.reachability_table_lock.acquire()

        if not self.neighbors:
            print("The neighbors table is empty.")

        else:
            for (ip, port), (mask, cost) in self.neighbors.items():
                print(f"Address: {ip}:{port},",
                      f"mask: {mask}, cost: {cost}.")

        self.reachability_table_lock.release()

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Incorrect arg number")
        sys.exit(1)

    # Parse neighbors
    neighbors_string = {}
    for i in range(1, (len(sys.argv) - 4) // 4 + 1):
        index = i*4
        neighbors_string[sys.argv[index], int(sys.argv[index + 1]), int(sys.argv[index + 2])] = int(sys.argv[index + 3])
    node = UDPNode(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), neighbors_string)
    node.start_node()

