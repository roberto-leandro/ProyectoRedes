#!/usr/bin/env python3
import sys
import struct
import socket
import selectors
import threading
import utility
import time

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
PKT_TYPE_SIZE         = 1
BUFFER_SIZE = 2048  # Will be used when reading from a socket TODO reads from the socket should be dynamic

# Time intervals in seconds
SEND_TABLE_UPDATE_INTERVAL = 1
SEND_KEEP_ALIVE_INTERVAL = 3000  # SEND_TABLE_UPDATE_INTERVAL*1.5

# Various timeouts
SELECTOR_TIMEOUT = .5
SOCKET_TIMEOUT = 5.0
KEEP_ALIVE_TIMEOUT = 0.5
KEEP_ALIVE_RETRIES = 5


class UDPNode:

    def __init__(self, ip, mask, port, neighbors):
        # Simple data
        self.port = port
        self.ip = ip
        self.mask = mask
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.ip, self.port))
        self.sock.setblocking(True) #TODO should be true

        self.updates_to_ignore = 0

        # Structures
        # Reachability table: ip, port : mask, (ip, port), cost
        self.reachability_table = {}
        # Neighbors: ip, port : mask, cost,  current_retries (0 if node is dead), Timer obj
        self.neighbors = {}
        for (n_ip, n_mask, n_port), n_cost in neighbors.items():
            self.neighbors[(n_ip, n_port)] = (n_mask, n_cost, KEEP_ALIVE_RETRIES, None)
            self.reachability_table[(n_ip, n_port)] = (n_mask, (n_ip, n_port), n_cost)  # FIXME should not be filled yet

        # Locks
        self.reachability_table_lock = threading.Lock()
        self.neighbors_lock = threading.Lock()

        # Events
        self.stopper = threading.Event()

        # Threads
        self.connection_handler_thread = threading.Thread(target=self.handle_incoming_connections)
        self.keep_alive_handler_thread = threading.Thread(target=self.send_keep_alive_loop)
        self.update_handler_thread = threading.Thread(target=self.send_updates_loop)
        self.command_handler_thread = threading.Thread(target=self.handle_console_commands)

        # Prints identifying the node
        print(f"Welcome to node {ip}:{port}/{mask}!")
        print(f"\nThis node's neighbors:")
        self.print_neighbors_table()
        print("\nAvailable commands are:")
        print("    sendMessage <ip> <port> <message>")
        print("    exit")
        print("    printTable")
        print("    printNeighbors\n")

    def start_node(self):
        # Start the thread that will listen and respond to console commands
        self.command_handler_thread.start()

        # Start the thread that manages keep alives
        self.keep_alive_handler_thread.start()

        # This thread will periodically send updates
        self.update_handler_thread.start()

        # Start the thread that handles incoming messages
        self.connection_handler_thread.start()

    def send_updates_loop(self):
        self.send_update()
        a = 0
        while not self.stopper.wait(SEND_TABLE_UPDATE_INTERVAL):
            self.send_update()
            a += 1
            if a == 10:
                break
        print("Finished the update sending loop!")

    def send_update(self):
        for (ip, port) in self.neighbors:
            self.send_reachability_table(ip, port)

    def send_keep_alive_loop(self):
        while not self.stopper.wait(SEND_KEEP_ALIVE_INTERVAL):
            with self.neighbors_lock:
                for (ip, port), (mask, cost, current_retries, _) in self.neighbors.items():
                    if current_retries > 0:
                        print(f"Sending keep alive to {ip}:{port}...")
                        timeout_timer = threading.Timer(KEEP_ALIVE_TIMEOUT,
                                                        self.handle_keep_alive_timeout, [], {"ip": ip, "port": port})
                        timeout_timer.start()
                        self.neighbors[(ip, port)] = (mask, cost, current_retries, timeout_timer)
                        self.send_keep_alive(ip, port)
        print("Finished the send keep alive loop!")

    def handle_keep_alive_timeout(self, **kwargs):
        # Get the parameters from the kwargs dictionary
        ip = kwargs["ip"]
        port = kwargs["port"]

        with self.neighbors_lock:
            # Check the neighbor's retry status
            neighbor = self.neighbors[ip, port]

            if neighbor[2] == 1:
                # If decreasing the remaining retries would set it to 0, remove the entry and start a flood
                print(f"Keep alive message to {ip}:{port} timed out! No more retries remaining, deleting entry and "
                      f"starting flood...")
                self.neighbors[ip, port] = (neighbor[0], neighbor[1], neighbor[2] - 1, None)
                self.remove_reachability_table_entry(ip, port)
                # TODO uncomment
                #self.send_flood_message(HOP_NUMBER)
            elif neighbor[2] > 0:
                # If the neighbor is not already at 0 retries, decrease the remaining retries
                self.neighbors[ip, port] = (neighbor[0], neighbor[1], neighbor[2]-1, None)
                print(f"Keep alive message to {ip}:{port} timed out! {neighbor[2]} retries remaining...")

    def handle_incoming_connections(self):
        main_selector = selectors.DefaultSelector()
        main_selector.register(self.sock, selectors.EVENT_READ)

        while not self.stopper.is_set():
            self.receive_message(self.sock)
        print("Finished the handle incoming connections loop!")

    def receive_message(self, connection):
        # Read enough bytes for the message, a standard packet does not exceed 1500 bytes
        try:
            message, address = connection.recvfrom(BUFFER_SIZE)
        except ConnectionResetError:
            print("the thing happened oh no")
            return

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

        elif message_type == PKT_TYPE_ACK_KEEP_ALIVE:
            print("MESSAGE: Received of type ACK_KEEP_ALIVE")
            with self.neighbors_lock:
                # Cancel the timer
                neighbor = self.neighbors[address]
                try:
                    neighbor[3].cancel()
                except AttributeError:
                    pass

                # If the node was thought dead re-add it to the reachability table
                if neighbor[2] == 0:
                    with self.reachability_table_lock:
                        self.reachability_table[address] = (neighbor[0], address, neighbor[1])

                # Reset the retry number
                self.neighbors[address] = (neighbor[0], neighbor[1], KEEP_ALIVE_RETRIES, None)

        elif message_type == PKT_TYPE_FLOOD:
            hops = struct.unpack("!B", message[1:2])[0]
            print(f"MESSAGE: Received of type FLOOD: with {hops} hops")
            print("UPDATE: Flushing reachability table")
            with self.reachability_table_lock:
                self.reachability_table.clear()
            self.send_flood_message(hops - 1)
            self.updates_to_ignore = SKIPPED_UPDATES_AFTER_FLOOD + 1

        elif message_type == PKT_TYPE_DATA_MSG:
            # Get the message's destination and size
            message_bytes = struct.unpack('!BBBBHB', message[PKT_TYPE_SIZE:PKT_TYPE_SIZE+7])

            ip_bytes = message[1:5]
            ip = f"{ip_bytes[0]}.{ip_bytes[1]}.{ip_bytes[2]}.{ip_bytes[3]}"
            port = int.from_bytes(message[5:7], byteorder='big', signed=False)
            size = int.from_bytes(message[7:8], byteorder='big', signed=False)
            str_message = message[8:].decode()

            if ip == self.ip and port == self.port:
                print(f"Received the data message {str_message}!")
            else:
                print(f"Received the mesage {str_message} headed for {ip}:{port}! Rerouting...")
                self.send_data_message(ip, port, str_message)

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

        # Message type
        struct.pack_into("!B", encoded_message, 0, PKT_TYPE_UPDATE)

        # 2 bytes for the amount of tuples
        struct.pack_into("!H", encoded_message, PKT_TYPE_SIZE, table_size)

        # Iterate the reachability table, writing each tuple to the encoded_message buffer
        offset = PKT_TYPE_SIZE + TUPLE_COUNT_SIZE  # will to the next empty space in the buffer
        for (r_ip, r_port), (r_mask, _, r_cost) in self.reachability_table.items():
            ip_tuple = tuple([int(tok) for tok in r_ip.split('.')])
            encoded_message[offset:offset + TUPLE_SIZE] = utility.encode_tuple(ip_tuple, r_port, r_mask, r_cost)
            offset += TUPLE_SIZE
        self.reachability_table_lock.release()
        if table_size > 0:
            self.send_message(ip, port, encoded_message)

    def handle_console_commands(self):
        while not self.stopper.is_set():
            print("imma read")
            try:
                pass
                command = input("Enter your command...\n> ")
            except EOFError:
                print(f"EOFILE {self.ip}")
                continue
            command = command.strip().split(" ")

            if len(command) == 0:
                print("Please enter a valid command.")
                continue

            elif command[0] == "sendMessage":
                if len(command) != 4:
                    print("Please enter a valid command.")
                    continue
                else:
                    self.send_data_message(command[1], int(command[2]), command[3])

            elif command[0] == "exit" or command[0] == "deleteNode":
                self.stop_node()

            elif command[0] == "printTable":
                self.print_reachability_table()

            elif command[0] == "printNeighbors":
                self.print_neighbors_table()

            else:
                print("Unrecognized command, try again.")

    def decode_tuples(self, message, origin_node):
        offset = 0
        tuple_bytes = bytearray(10)
        while offset < len(message):
            # Unpack the binary
            tuple_bytes = struct.unpack('!BBBBBBBBBB', message[offset:offset + TUPLE_SIZE])

            # Get each of the tuple's values
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

    def remove_reachability_table_entry(self, ip, port):
        with self.reachability_table_lock:
            if (ip, port) in self.reachability_table:
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

    def send_data_message(self, ip, port, str_message):
        bytes_message = str_message.encode()

        ip_tuple = tuple([int(tok) for tok in ip.split('.')])

        header = bytearray(8)
        struct.pack_into("!B", header, 0, PKT_TYPE_DATA_MSG)
        struct.pack_into("!BBBB", header, 1, ip_tuple[0], ip_tuple[1], ip_tuple[2], ip_tuple[3])
        struct.pack_into("!H", header, 5, port)
        struct.pack_into("!B", header, 7, len(bytes_message))

        if (ip, port) in self.reachability_table:
            route_address = self.reachability_table[ip, port][1]
            print(f"Routing the message {str_message} through node {route_address[0]}:{route_address[1]}")
            self.send_message(route_address[0], route_address[1], header+bytes_message)
        else:
            print(f"Received a message headed for {ip}:{port} but this node cannot reach it!")

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
            for (ip, port), (mask, cost, current_retries, _) in self.neighbors.items():
                print(f"Address: {ip}:{port},",
                      f"mask: {mask}, cost: {cost}, current keep alive retries: {current_retries}/{KEEP_ALIVE_RETRIES}")

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

