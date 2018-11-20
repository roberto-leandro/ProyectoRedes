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


class UDPNode(AbstractNode):
    SOCKET_TYPE = socket.SOCK_DGRAM
    NODE_TYPE_STRING = "[IntAS Node]"
    BUFFER_SIZE = 2048  # Will be used when reading from a socket
    SELECTOR_TIMEOUT = .5
    UPDATE_INTERVAL = 5

    def __init__(self, ip, port, mask, neighbors):
        super().__init__(ip, port)
        self.mask = mask
        self.reachability_table = \
            {(n_ip, n_mask): ((n_ip, n_port), n_cost)
             for (n_ip, n_mask, n_port), n_cost in neighbors.items()}
        self.neighbors = \
            {(n_ip, n_port): n_cost
             for (n_ip, n_mask, n_port), n_cost in neighbors.items()}
        # TODO: lock?
        self.updates_to_ignore = 0
        self.neighbors_lock = threading.Lock()

    def start_node(self):
        super().start_node()
        while not self.stopper.is_set():
            time.sleep(self.UPDATE_INTERVAL)
            self.update_route()

    def update_route(self):
        for (ip, port) in self.neighbors:
            self.send_reachability_table(ip, port)

    def update_reachability_table(self, net_address, node_address, cost):
        with self.neighbors_lock:
            total_cost = cost + self.neighbors[node_address]
        super().update_reachability_table(net_address, node_address, total_cost)

    def handle_incoming_connections(self):
        self.sock.bind((self.ip, self.port))
        self.sock.setblocking(False)
        main_selector = selectors.DefaultSelector()
        main_selector.register(self.sock, selectors.EVENT_READ)

        while not self.stopper.is_set():
            events = main_selector.select(UDPNode.SELECTOR_TIMEOUT)
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
        message, address = connection.recvfrom(self.BUFFER_SIZE)
        print(f"MESSAGE: Connected with {address}")
        message_type = message[0]

        if message_type == PKT_TYPE_UPDATE:
            if self.updates_to_ignore > 0:
                return [], ""
            triplet_count = struct.unpack('!H', message[1:3])[0]
            print(f"MESSAGE: Received of type UPDATE with {triplet_count} triplets.")
            # TODO: does n = 0 still means disconnect in a update packet?
            if triplet_count == 0:
                self.disconnect_address(address)
                return [], ""
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
        encoded_message = bytearray(3 + self.TRIPLET_SIZE*table_size)
        struct.pack_into("!B", encoded_message, 0, PKT_TYPE_UPDATE)
        struct.pack_into("!H", encoded_message, 1, table_size)
        offset = 3
        for (r_ip, r_mask), (_, r_cost) in self.reachability_table.items():
            ip_tuple = tuple([int(tok) for tok in r_ip.split('.')])
            encoded_message[offset:offset+self.TRIPLET_SIZE] = self.encode_triplet(ip_tuple, r_mask, r_cost)
            offset += self.TRIPLET_SIZE
        self.reachability_table_lock.release()
        if table_size > 0:
            self.send_message(ip, port, encoded_message)

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


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(sys.argv)
        print(len(sys.argv))
        print("Incorrect arg number")
        sys.exit(1)

    node = UDPNode(sys.argv[1], int(sys.argv[2]))
    node.start_node()

