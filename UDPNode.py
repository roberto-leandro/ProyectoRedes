#!/usr/bin/env python3
import sys
import time
import struct
import socket
import selectors
import threading
from AbstractNode import AbstractNode

PKT_TYPE_UPDATE         = 1
PKT_TYPE_KEEP_ALIVE     = 2
PKT_TYPE_ACK_KEEP_ALIVE = 3
PKT_TYPE_FLOOD          = 4
PKT_TYPE_DATA_MSG       = 5
PKT_TYPE_COST_CHANGE    = 6
PKT_TYPE_DEAD           = 7
HOP_NUMBER = 50
SKIPPED_UPDATES_AFTER_FLOOD = 3
NODE_TYPE_STRING = "[IntAS Node]"
BUFFER_SIZE = 2048  # Will be used when reading from a socket
SELECTOR_TIMEOUT = .5
UPDATE_INTERVAL = 1
HEADER_SIZE = 2
TRIPLET_SIZE = 8
SOCKET_TIMEOUT = 5.0

class UDPNode:

    def __init__(self, ip, mask, port, neighbors):
        # Simple data
        self.port = port
        self.ip = ip
        self.mask = mask
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.updates_to_ignore = 0

        # Structures
        # Reachability table: ip, port : mask, (ip, port), cost
        self.reachability_table = {}
        # Neighbors: ip, port : mask, cost, Timer obj, current_retries (0 if node is dead)
        self.neighbors = {}
        for neighbor, n_cost in neighbors.items():
            # neighbor = (ip, mask, port)
            self.neighbors[(neighbor[0], neighbor[2])] = (neighbor[1], n_cost)
            self.reachability_table[(neighbor[0], neighbor[1])] = ((neighbor[0], neighbor[2]), n_cost)
            #self.reachability_table[(neighbor[0], neighbor[1])] = (mask, (neighbor[0], neighbor[2]), n_cost)

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
        connection_handler_thread = \
            threading.Thread(target=self.handle_incoming_connections)
        connection_handler_thread.start()
        while not self.stopper.is_set():
            time.sleep(UPDATE_INTERVAL)
            self.update_route()
        print("Finished the update msending loop!")

    def update_route(self):
        for (ip, port) in self.neighbors:
            self.send_reachability_table(ip, port)

    def update_reachability_table(self, net_address, node_address, cost):
        with self.neighbors_lock:
            total_cost = cost + self.neighbors[node_address][1]

        # Write to the reachability table,
        # as many threads may perform read/write we need to lock it
        with self.reachability_table_lock:
            if net_address not in self.reachability_table or \
                    self.reachability_table[net_address][1] > total_cost:
                self.reachability_table[net_address] = (node_address, total_cost)

    def handle_incoming_connections(self):
        self.sock.bind((self.ip, self.port))
        self.sock.setblocking(False)
        main_selector = selectors.DefaultSelector()
        main_selector.register(self.sock, selectors.EVENT_READ)

        while not self.stopper.is_set():
            events = main_selector.select(SELECTOR_TIMEOUT)
            for _ in events:
                if self.stopper.is_set():
                    break
                message, address = self.receive_message(self.sock, None)
                self.decode_message(message, address)

    def disconnect_neighbor(self, address):
        with self.neighbors_lock:
            self.neighbors.pop(address, default=None)
        self.disconnect_address(address)
        # Probably should start a flood

    def disconnect_address(self, address):
        self.reachability_table_lock.acquire()
        # Generate a new list without address
        self.reachability_table = \
            {key: value
             for key, value in self.reachability_table.items()
             if value[0] != address}
        self.reachability_table_lock.release()
        print(f"DISCONNECT: Deleting {address} table entries")

    def receive_message(self, connection, address):
        # Read enough bytes for the message, a standard packet does not exceed 1500 bytes
        message, address = connection.recvfrom(BUFFER_SIZE)
        print(f"MESSAGE: Connected with {address}")
        message_type = message[0]

        if message_type == PKT_TYPE_UPDATE:
            if self.updates_to_ignore > 0:
                self.updates_to_ignore -= 1
                return [], ""
            triplet_count = struct.unpack('!H', message[1:3])[0]
            print(f"MESSAGE: Received of type UPDATE with {triplet_count} triplets.")
            # Return a buffer with only the triplets, omitting the header
            return message[3:], address
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
        return [], ""

    def send_message(self, ip, port, message):
        print(f"MESSAGE: Sending {len(message)} bytes to {ip}:{port}")
        self.sock.sendto(message, (ip, port))

    def send_reachability_table(self, ip, port):
        self.reachability_table_lock.acquire()
        table_size = len(self.reachability_table)
        encoded_message = bytearray(3 + TRIPLET_SIZE*table_size)
        struct.pack_into("!B", encoded_message, 0, PKT_TYPE_UPDATE)
        struct.pack_into("!H", encoded_message, 1, table_size)
        offset = 3
        for (r_ip, r_mask), (_, r_cost) in self.reachability_table.items():
            ip_tuple = tuple([int(tok) for tok in r_ip.split('.')])
            encoded_message[offset:offset+TRIPLET_SIZE] = self.encode_triplet(ip_tuple, r_mask, r_cost)
            offset += TRIPLET_SIZE
        self.reachability_table_lock.release()
        if table_size > 0:
            self.send_message(ip, port, encoded_message)

    def encode_triplet(self, address, net_mask, cost):
        message = bytearray(AbstractNode.TRIPLET_SIZE)
        # Each triplet is encoded with the following 8-byte format:
        # BBBB (4 bytes) network address
        #  B   (1 byte)  subnet mask
        #  I   (4 bytes) cost.
        #      The cost should only be 3 bytes, this is handled below.
        struct.pack_into('!BBBBB', message, 0,
                         address[0], address[1],
                         address[2], address[3],
                         net_mask)

        # Pack the cost into a 4 byte buffer
        cost_bytes = struct.pack('!I', cost)

        # Write the cost into the message buffer, copying only 3 bytes and omitting 1
        # The least significant byte is the one omitted because its encoded
        # as big endian
        message[5:8] = cost_bytes[1:]
        return message

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

    def decode_message(self, message, address):
        offset = 0
        while offset < len(message):
            # Unpack the binary
            triplet = struct.unpack('!BBBBBBBB', message[offset:offset+8])

            # Get each of the triplet's values
            ip_bytes = triplet[:4]
            ip = f"{ip_bytes[0]}.{ip_bytes[1]}.{ip_bytes[2]}.{ip_bytes[3]}"
            mask = triplet[4]
            cost = int.from_bytes(triplet[5:], byteorder='big', signed=False)

            offset += TRIPLET_SIZE
            print(f"ADDRESS: {ip}" +
                  f", SUBNET MASK: {mask}, COST: {cost}")
            net_address = (ip, mask)
            self.update_reachability_table(net_address, address, cost)

    def print_reachability_table(self):
        print("Current reachability table:")
        self.reachability_table_lock.acquire()

        if not self.reachability_table:
            print("The reachability table is empty.")

        else:
            for (ip, port), ((ip2, port2), cost) in self.reachability_table.items():
                print(f"Destiny: {ip}:{port},",
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
        print(f"{sys.argv[index]} {sys.argv[index+1]} {sys.argv[index+2]} {int(sys.argv[index+3])}")
        neighbors_string[sys.argv[index], int(sys.argv[index + 1]), int(sys.argv[index + 2])] = int(sys.argv[index + 3])
    node = UDPNode(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), neighbors_string)
    node.start_node()

