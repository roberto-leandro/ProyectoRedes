#!/usr/bin/env python3
import sys
import struct
import socket
import queue
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
SEND_NODE_AWAKEN_INTERVAL = 0.5
SEND_TABLE_UPDATE_INTERVAL = 10  # 30
SEND_KEEP_ALIVE_INTERVAL = 5  # SEND_TABLE_UPDATE_INTERVAL * 2
IGNORE_AFTER_FLOOD_INTERVAL = 5  # SEND_TABLE_UPDATE_INTERVAL * 3

# Various timeouts in seconds
SOCKET_TIMEOUT = 0.05
KEEP_ALIVE_TIMEOUT = 0.05
KEEP_ALIVE_RETRIES = 5


class UDPNode:

    def __init__(self, ip, mask, port, neighbors):
        # Simple data
        self.port = port
        self.ip = ip
        self.mask = mask
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.ip, self.port))
        self.sock.setblocking(True)
        self.sock.settimeout(SOCKET_TIMEOUT)

        # Structures
        # Reachability table: ip, port : mask, (ip, port), cost
        self.reachability_table = {}
        # Neighbors: ip, port : mask, cost,  current_retries (0 if node is dead), Timer obj
        self.neighbors = {}
        for (n_ip, n_mask, n_port), n_cost in neighbors.items():
            self.neighbors[(n_ip, n_port)] = (n_mask, n_cost, 0, None)

        # Used to wake up nodes
        self.unawakened_neighbors = list(self.neighbors.keys())

        # Queue to hold incoming messages
        # Will be flushed when encountering a flood
        self.message_queue = queue.Queue()

        # Locks
        self.reachability_table_lock = threading.Lock()
        self.neighbors_lock = threading.Lock()
        self.message_queue_lock = threading.Lock()

        # Events
        self.stopper = threading.Event()
        self.ignore_updates = threading.Event()

        # Threads
        self.connection_handler_thread = threading.Thread(target=self.handle_incoming_connections_loop)
        self.neighbor_init_thread = threading.Thread(target=self.neighbor_init_loop)
        self.message_reader_thread = threading.Thread(target=self.read_messages_loop)
        self.keep_alive_handler_thread = threading.Thread(target=self.send_keep_alive_loop)
        self.update_handler_thread = threading.Thread(target=self.send_updates_loop)
        self.command_handler_thread = threading.Thread(target=self.handle_console_commands)

        # Prints identifying the node
        utility.log_message(f"Welcome to node {ip}:{port}/{mask}!")
        utility.log_message(f"\nThis node's neighbors:")
        self.print_neighbors_table()
        utility.log_message("\nAvailable commands are:")
        utility.log_message("    sendMessage <ip> <port> <message>")
        utility.log_message("    exit")
        utility.log_message("    printOwn")
        utility.log_message("    printTable")
        utility.log_message("    printNeighbors\n")

    def start_node(self):
        # Start the thread that handles incoming messages
        self.connection_handler_thread.start()

        # Start the thread that reads messages and puts them in a queue
        self.message_reader_thread.start()

        # Start the thread that checks if the node's neighbors are alive
        self.neighbor_init_thread.start()

        # Start the thread that will listen and respond to console commands
        self.command_handler_thread.start()

        # Start the thread that manages keep alives
        self.keep_alive_handler_thread.start()

        # This thread will periodically send updates
        self.update_handler_thread.start()

    def read_messages_loop(self):
        while not self.stopper.is_set():
            try:
                message, address = self.sock.recvfrom(BUFFER_SIZE)
            except socket.timeout:
                continue
            except ConnectionResetError:
                utility.log_message("Received a Windows exception informing us that a connection died...")
                continue

            if self.ignore_updates.is_set():
                # Continue without putting the message in the queue if a flood occurred recently
                continue

            with self.message_queue_lock:
                self.message_queue.put((message, address))
        utility.log_message("Finished the read messages loop!")

    def neighbor_init_loop(self):
        while not self.stopper.wait(SEND_NODE_AWAKEN_INTERVAL) and self.unawakened_neighbors:
            for (ip, port) in self.unawakened_neighbors:
                utility.log_message(f"Waking {ip}:{port}")
                self.send_keep_alive(ip, port)
        utility.log_message("All neighbors have awakened!")

    def send_updates_loop(self):
        self.send_update()
        a = 0
        while not self.stopper.wait(SEND_TABLE_UPDATE_INTERVAL):
            self.send_update()
            a += 1
            if a == 4:
                break
        utility.log_message("Finished the update sending loop!")

    def send_update(self):
        for (ip, port) in self.neighbors:
            self.send_reachability_table(ip, port)

    def send_keep_alive_loop(self):
        while not self.stopper.wait(SEND_KEEP_ALIVE_INTERVAL):
            with self.neighbors_lock:
                for (ip, port), (mask, cost, current_retries, _) in self.neighbors.items():
                    if current_retries > 0:
                        utility.log_message(f"Sending keep alive to {ip}:{port}...")
                        timeout_timer = threading.Timer(KEEP_ALIVE_TIMEOUT,
                                                        self.handle_keep_alive_timeout, [], {"ip": ip, "port": port})
                        timeout_timer.start()
                        self.neighbors[(ip, port)] = (mask, cost, current_retries, timeout_timer)
                        self.send_keep_alive(ip, port)
        utility.log_message("Finished the send keep alive loop!")

    def handle_keep_alive_timeout(self, **kwargs):
        # Get the parameters from the kwargs dictionary
        ip = kwargs["ip"]
        port = kwargs["port"]

        with self.neighbors_lock:
            # Check the neighbor's retry status
            neighbor = self.neighbors[ip, port]

            if neighbor[2] == 1:
                # If decreasing the remaining retries would set it to 0, remove the entry and start a flood
                utility.log_message(f"Keep alive message to {ip}:{port} timed out! No more retries remaining, deleting "
                                    f"entry and starting flood...")
                self.neighbors[ip, port] = (neighbor[0], neighbor[1], neighbor[2] - 1, None)
                self.remove_reachability_table_entry(ip, port)
                # TODO uncomment
                #self.send_flood_message(HOP_NUMBER)
            elif neighbor[2] > 0:
                # If the neighbor is not already at 0 retries, decrease the remaining retries
                self.neighbors[ip, port] = (neighbor[0], neighbor[1], neighbor[2]-1, None)
                utility.log_message(f"Keep alive message to {ip}:{port} timed out! {neighbor[2]} retries remaining...")

    def handle_incoming_connections_loop(self):
        while not self.stopper.is_set():
            self.receive_message(self.sock)
        utility.log_message("Finished the handle incoming connections loop!")

    def receive_message(self, connection):
        # Read enough bytes for the message, a standard packet does not exceed 1500 bytes
        try:
            message, address = self.message_queue.get(block=True, timeout=SOCKET_TIMEOUT)
        except queue.Empty:
            return

        message_type = int.from_bytes(message[0:PKT_TYPE_SIZE], byteorder='big', signed=False)

        if message_type == PKT_TYPE_UPDATE:
            tuple_count = struct.unpack('!H', message[PKT_TYPE_SIZE:PKT_TYPE_SIZE + 2])[0]
            utility.log_message(f"Received a table update from {address[0]}:{address[1]} of size "
                                f"{len(message)} with {tuple_count} tuples.")
            # Decode the received tuples and update the reachability table if necessary
            self.decode_tuples(message[PKT_TYPE_SIZE + TUPLE_COUNT_SIZE:], address)

        elif message_type == PKT_TYPE_KEEP_ALIVE:
            utility.log_message(f"Received a keep alive from {address[0]}:{address[1]}.")
            self.send_ack_keep_alive(address[0], address[1])

        elif message_type == PKT_TYPE_ACK_KEEP_ALIVE:
            utility.log_message(f"Received a keep alive ack from {address[0]}:{address[1]}.")
            # Check if this is the first time the node has replied
            if address in self.unawakened_neighbors:
                utility.log_message(f"Neighbor {address[0]}:{address[1]} has woken up!")
                self.unawakened_neighbors.remove(address)

            with self.neighbors_lock:
                # Cancel the timer
                neighbor = self.neighbors[address]
                try:
                    neighbor[3].cancel()
                except AttributeError:
                    pass

                # If the node was thought dead re-add it to the reachability table
                with self.reachability_table_lock:
                    self.reachability_table[address] = (neighbor[0], address, neighbor[1])

                # Reset the retry number
                self.neighbors[address] = (neighbor[0], neighbor[1], KEEP_ALIVE_RETRIES, None)

        elif message_type == PKT_TYPE_FLOOD:
            hops = struct.unpack("!B", message[1:2])[0]
            utility.log_message(f"Received a FLOOD: with {hops} hops remaining from {address[0]}:{address[1]}."
                                f"\nFlushing reachability table..."
                                f"\nWill ignore updates for {IGNORE_AFTER_FLOOD_INTERVAL} seconds.")

            # Continue the flood with one less hop
            self.send_flood_message(hops - 1)

        elif message_type == PKT_TYPE_DATA_MSG:
            ip_bytes = message[1:5]
            ip = f"{ip_bytes[0]}.{ip_bytes[1]}.{ip_bytes[2]}.{ip_bytes[3]}"
            port = int.from_bytes(message[5:7], byteorder='big', signed=False)
            size = int.from_bytes(message[7:8], byteorder='big', signed=False)
            str_message = message[8:].decode()

            if ip == self.ip and port == self.port:
                utility.log_message(f"Received the data message {str_message} from {address[0]}:{address[1]}!")
            else:
                utility.log_message(f"Received the message {str_message} headed for {ip}:{port} from "
                                    f"{address[0]}:{address[1]}! Rerouting...")
                self.send_data_message(ip, port, str_message)

        elif message_type == PKT_TYPE_DEAD:
            utility.log_message(f"Neighbor {address[0]}:{address[1]} will DIE!"
                                f"\nFlushing reachability table and starting flood..."
                                f"\nWill ignore updates for {IGNORE_AFTER_FLOOD_INTERVAL} seconds.")

            # Start a flood with neighbors
            self.send_flood_message(HOP_NUMBER)

        elif message_type == PKT_TYPE_COST_CHANGE:
            utility.log_message(f"Neighbor changed cost! Flushing table and starting flood..."
                                f"\nWill ignore updates for {IGNORE_AFTER_FLOOD_INTERVAL} seconds.")
            # Start a flood with neighbors
            self.send_flood_message(HOP_NUMBER)

    def reset_ignore_updates(self):
        utility.log_message("Resuming message listening...")

        self.ignore_updates.clear()

        # Awaken neighbors again
        self.neighbor_init_thread = threading.Thread(target=self.neighbor_init_loop)
        self.neighbor_init_thread.start()

    def send_message(self, ip, port, message):
        utility.log_message(f"Sending {len(message)} bytes to {ip}:{port}")
        self.sock.sendto(message, (ip, port))

    def send_reachability_table(self, ip, port):
        self.reachability_table_lock.acquire()
        table_size = len(self.reachability_table)

        # Should not send an entry with the receiver's own address
        if (ip, port) in self.reachability_table:
            table_size -= 1

        if table_size <= 0:
            self.reachability_table_lock.release()
            return

        encoded_message = bytearray(PKT_TYPE_SIZE + TUPLE_COUNT_SIZE + TUPLE_SIZE * table_size)

        # Message type
        struct.pack_into("!B", encoded_message, 0, PKT_TYPE_UPDATE)

        # 2 bytes for the amount of tuples
        struct.pack_into("!H", encoded_message, PKT_TYPE_SIZE, table_size)

        # Iterate the reachability table, writing each tuple to the encoded_message buffer
        offset = PKT_TYPE_SIZE + TUPLE_COUNT_SIZE  # will to the next empty space in the buffer
        for (r_ip, r_port), (r_mask, _, r_cost) in self.reachability_table.items():
            # Add entry  to message only if it does not refer to the receiving node
            if r_ip == ip and r_port == port:
                continue
            ip_tuple = tuple([int(tok) for tok in r_ip.split('.')])
            encoded_message[offset:offset + TUPLE_SIZE] = utility.encode_tuple(ip_tuple, r_port, r_mask, r_cost)
            offset += TUPLE_SIZE
        self.reachability_table_lock.release()

        self.send_message(ip, port, encoded_message)

    def handle_console_commands(self):
        while not self.stopper.is_set():
            try:
                pass
                command = input("Enter your command...\n> ")
            except EOFError:
                utility.log_message(f"EOFile while expecting user input...")
                continue
            command = command.strip().split(" ")

            if len(command) == 0:
                utility.log_message("Please enter a valid command.")
                continue

            elif command[0] == "sendMessage":
                if len(command) != 4:
                    utility.log_message("Please enter a valid command.")
                    continue
                else:
                    self.send_data_message(command[1], int(command[2]), command[3])

            elif command[0] == "exit" or command[0] == "deleteNode":
                self.stop_node()

            elif command[0] == "printTable":
                self.print_reachability_table()

            elif command[0] == "printOwn":
                utility.log_message(f"This node's information: {self.ip}:{self.port}/{self.mask}")

            elif command[0] == "printNeighbors":
                self.print_neighbors_table()

            else:
                utility.log_message("Unrecognized command, try again.")

    def decode_tuples(self, message, origin_node):
        # Ignore updates that do not originate from a neighbor
        if origin_node not in self.neighbors:
            utility.log_message(f"Discarding update from {origin_node[0]}:{origin_node[1]} as it is not a neighbor.")
            return

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
            utility.log_message(f"ADDRESS: {ip}, SUBNET MASK: {mask}, COST: {cost}")

            self.update_reachability_table(ip, port, mask, cost, origin_node)

    def update_reachability_table(self, ip, port, mask, cost, through_node):
        with self.neighbors_lock:
            total_cost = cost + self.neighbors[through_node][1]

        # Write to the reachability table,
        # as many threads may perform read/write we need to lock it
        with self.reachability_table_lock:
            if (ip, port) not in self.reachability_table or self.reachability_table[(ip, port)][2] > total_cost:
                utility.log_message(f"Changing cost of {ip}:{port} passing through {through_node}.")
                self.reachability_table[(ip, port)] = (mask, through_node, total_cost)

    def remove_reachability_table_entry(self, ip, port):
        with self.reachability_table_lock:
            if (ip, port) in self.reachability_table:
                del self.reachability_table[(ip, port)]
        utility.log_message(f"DISCONNECT: Deleted {ip}:{port} from the reachability table.")

    def send_flood_message(self, hops):
        message = bytearray(2)
        struct.pack_into("!B", message, 0, PKT_TYPE_FLOOD)
        struct.pack_into("!B", message, 1, hops)
        for ip, port in self.neighbors:
            self.send_message(ip, port, message)
        # Set the event to indicate that updates should be ignored
        self.ignore_updates.set()

        # Clear the reachability table and message queue
        with self.reachability_table_lock:
            self.reachability_table.clear()
        with self.message_queue_lock:
            self.message_queue = queue.Queue()

        # Start a timer to clear the previous event so updates can continue
        continue_updates_timer = threading.Timer(IGNORE_AFTER_FLOOD_INTERVAL, self.reset_ignore_updates)
        continue_updates_timer.start()

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
            utility.log_message(f"Routing the message {str_message} through node {route_address[0]}:{route_address[1]}")
            self.send_message(route_address[0], route_address[1], header+bytes_message)
        else:
            utility.log_message(f"Received a message headed for {ip}:{port} but this node cannot reach it!")

    def send_node_death_message(self, ip, port):
        message = bytearray(1)
        struct.pack_into("!B", message, 0, PKT_TYPE_DEAD)
        self.send_message(ip, port, message)

    def stop_node(self):
        utility.log_message("EXIT: Killing node, waiting for threads to finish...")

        # Set this flag to false, stopping all loops
        self.stopper.set()

        # Join all threads except command console handler, as this is that thread
        self.connection_handler_thread.join()
        self.neighbor_init_thread.join()
        self.message_reader_thread.join()
        self.keep_alive_handler_thread.join()
        self.update_handler_thread.join()

        # Send a message to all neighbors indicating that this node will die
        self.reachability_table_lock.acquire()
        for ip, port in self.neighbors:
            self.send_node_death_message(ip, port)
        self.reachability_table_lock.release()

    def print_reachability_table(self):
        utility.log_message("Current reachability table:")
        self.reachability_table_lock.acquire()

        if not self.reachability_table:
            utility.log_message("The reachability table is empty.")

        else:
            for (ip, port), (mask, (ip2, port2), cost) in self.reachability_table.items():
                utility.log_message(f"Destiny: {ip}:{port}/{mask}, through: {ip2}:{port2}, cost: {cost}.")

        self.reachability_table_lock.release()

    def print_neighbors_table(self):
        utility.log_message("Neighbors:")
        self.reachability_table_lock.acquire()

        if not self.neighbors:
            utility.log_message("The neighbors table is empty.")

        else:
            for (ip, port), (mask, cost, current_retries, _) in self.neighbors.items():
                utility.log_message(f"Address: {ip}:{port}, mask: {mask}, cost: {cost}, "
                                    f"current keep alive retries: {current_retries}/{KEEP_ALIVE_RETRIES}")

        self.reachability_table_lock.release()

if __name__ == "__main__":
    if len(sys.argv) < 4:
        utility.log_message("Incorrect argument number, exiting...")
        sys.exit(1)

    # Parse neighbors
    neighbors_string = {}
    for i in range(1, (len(sys.argv) - 4) // 4 + 1):
        index = i*4
        neighbors_string[sys.argv[index], int(sys.argv[index + 1]), int(sys.argv[index + 2])] = int(sys.argv[index + 3])
    node = UDPNode(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), neighbors_string)
    node.start_node()

