import threading
import struct
import sys
import readline
import socket


class TCPNode:
    TRIPLET_SIZE = 8

    def __init__(self, ip, port):
        self.port = port
        self.ip = ip
        self.routing_table = {}
        self.reachability_table = {}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print("[PseudoBGP Node]")
        print("Address:", ip)
        print("Port:", port)

    def start_node(self):
        """ Create two new threads
        one to handle console commands and
        another to listen to incoming connections. """
        print("START EXECUTED")
        connection_handler_thread =\
            threading.Thread(target=self.handle_incoming_connections)
        connection_handler_thread.start()
        self.handle_console_commands()

    def handle_incoming_connections(self):
        print("LISTENING TO INCOMING CONNECTIONS")
        self.sock.bind((self.ip, self.port))
        self.sock.listen(self.port)

        while True:
            conn, addr = self.sock.accept()
            print("CONNECTED WITH {addr}")
            with conn:

                # The first 2 bytes contain the amount of triplets in the message
                length = struct.unpack('!H', conn.recv(2))[0]
                print('RECEIVED A MESSAGE WITH', length, 'TRIPLETS:')

                for i in range(0, length):
                    # Read the first 5 bytes, which contain the address and mask.
                    # Each triplet has 8 bytes, so 3 bytes remain.
                    message = conn.recv(self.TRIPLET_SIZE-3)
                    triplets = struct.unpack('!BBBBB', message)

                    # Read the last 3 bytes (representing the cost), and interpret them as an int.
                    cost = int.from_bytes(conn.recv(3), byteorder='big', signed=False)
                    print('ADDRESS: ', triplets[0], '.', triplets[1], '.', triplets[2], '.', triplets[3],
                          ', SUBNET MASK: ', triplets[4], ', COST: ', cost, sep='')

    def send_message(self, ip, port, message):
        print("SENDING ", len(message), " BYTES TO ", ip, ":", port)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as host_socket:
            host_socket.connect((ip, port))
            host_socket.sendall(message)

    def handle_console_commands(self):
        while True:
            command = input("Enter your command...\n> ")
            command = command.strip().split(" ")

            if len(command) != 4:
                print("Unrecognized command, try again.")

            if command[0] == "sendMessage":
                message = self.read_message()
                self.send_message(ip=command[1], port=int(command[2]), message=message)
            elif command[0] == "exit":
                sys.exit(1)

    def stop_node(self):
        # Close all open connections and terminate all threads
        pass

    def read_message(self):
        length = int(input("Enter the length of your message...\n"))

        # The message will be 2 bytes (which represent the length) + the size of each triplet * the amount of triplets
        message = bytearray(2+length*self.TRIPLET_SIZE)

        # The first 2 bytes of the message (H is 2 bytes) should be the length of triplets in the message
        struct.pack_into("!H", message, 0, length)

        # Counts bytes already written, in order to add information in the right location of the message buffer
        offset = 2

        # Then add 8 bytes per triplet (4 for IP, 1 for mask, 3 for cost)
        for i in range(0, length):
            current_message = \
                input("Type the message to be sent as follows:\n<IP address> <subnet mask> <cost>\n")\
                .strip().split(' ')
            address = current_message[0].strip().split('.')

            # Each triplet is encoded with the following 8-byte format:
            # BBBB (4 bytes) network address
            # B    (1 byte)  subnet mask
            # I    (4 bytes) cost. The cost should only be 3 bytes, this is handled below.
            struct.pack_into('!BBBBB', message, offset, int(address[0]), int(address[1]), int(address[2]), int(address[3]), int(current_message[1]))

            # Pack the cost into a 4 byte buffer
            cost = struct.pack('!I', int(current_message[2]))

            # Write the cost into the message buffer, copying only 3 bytes
            # The least significant byte is the one dropped because its encoded as big endian
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
