#!/usr/bin/env python3
import sys
import time
import struct
import socket
import selectors
from AbstractNode import AbstractNode


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

    def start_node(self):
        super().start_node()
        while not self.stopper.is_set():
            time.sleep(self.UPDATE_INTERVAL)
            self.update_route()

    def update_route(self):
        for (ip, _, port) in self.neighbors:
            self.send_reachability_table(ip, port)

    def update_reachability_table(self, net_address, node_address, cost):
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

        # Get the header, located in the first 2 bytes
        triplet_count = struct.unpack('!H', message[0:2])[0]
        print(f"MESSAGE: Received a message with {triplet_count} triplets.")

        if triplet_count == 0:
            self.disconnect_address(address)
            return [], ""

        # Return a buffer with only the triplets, omitting the header
        return message[2:], address

    def send_message(self, ip, port, message):
        print(f"MESSAGE: Sending {len(message)} bytes to {ip}:{port}")
        self.sock.sendto(message, (ip, port))

    def send_reachability_table(self, ip, port):
        self.reachability_table_lock.acquire()
        table_size = len(self.reachability_table)
        encoded_message = bytearray(2 + self.TRIPLET_SIZE*table_size)
        struct.pack_into("!H", encoded_message, 0, table_size)
        offset = 2
        for (r_ip, r_mask), (_, r_cost) in self.reachability_table.items():
            ip_tuple = tuple([int(tok) for tok in r_ip.split('.')])
            encoded_message[offset:offset+self.TRIPLET_SIZE] = self.encode_triplet(ip_tuple, r_mask, r_cost)
            offset += self.TRIPLET_SIZE
        self.reachability_table_lock.release()
        if table_size > 0:
            self.send_message(ip, port, encoded_message)

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

